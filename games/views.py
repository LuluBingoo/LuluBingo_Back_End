from decimal import Decimal, ROUND_HALF_UP
import random
from datetime import datetime, timedelta
import math

from django.core.cache import cache
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse
from django.db import transaction as db_transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from transactions.models import Transaction
from transactions.services import apply_transaction

from .models import Game, ShopBingoSession
from .serializers import (
    GameClaimSerializer,
    GameCompleteSerializer,
    GameCreateSerializer,
    GameSerializer,
    ShopBingoCartellaSelectSerializer,
    ShopBingoConfirmPaymentSerializer,
    ShopBingoSessionCreateSerializer,
    ShopBingoSessionSerializer,
)


ALLOWED_GAME_STATUS_FILTERS = {choice[0] for choice in Game.Status.choices}
ALLOWED_TX_TYPE_FILTERS = {choice[0] for choice in Transaction.Type.choices}
ALLOWED_CLAIM_PATTERNS = {"row", "diagonal"}


def _generate_cartella_board() -> list[int]:
    numbers: list[int] = []
    ranges = [(1, 15), (16, 30), (31, 45), (46, 60), (61, 75)]
    for min_n, max_n in ranges:
        col = random.sample(range(min_n, max_n + 1), 5)
        numbers.extend(col)
    numbers[12] = 0
    return numbers


def _generate_unique_cartella_boards(count: int) -> list[list[int]]:
    if count <= 0:
        return []

    boards: list[list[int]] = []
    signatures: set[tuple[int, ...]] = set()
    attempts = 0
    max_attempts = max(count * 400, 400)

    while len(boards) < count:
        attempts += 1
        if attempts > max_attempts:
            raise ValueError("Failed to generate unique cartella boards")

        board = _generate_cartella_board()
        signature = tuple(board)
        if signature in signatures:
            continue

        signatures.add(signature)
        boards.append(board)

    return boards


def _format_called_number(number: int) -> str:
    if 1 <= number <= 15:
        return f"B{number}"
    if 16 <= number <= 30:
        return f"I{number}"
    if 31 <= number <= 45:
        return f"N{number}"
    if 46 <= number <= 60:
        return f"G{number}"
    return f"O{number}"


def _board_matches_pattern(
    board: list[int],
    called_set: set[int],
    pattern: str,
) -> bool:
    normalized = pattern.strip().lower()
    if len(board) != 25:
        return False

    def is_marked(value: int) -> bool:
        return value == 0 or value in called_set

    grid = [board[idx : idx + 5] for idx in range(0, 25, 5)]

    if normalized == "row":
        return any(all(is_marked(value) for value in row) for row in grid)

    if normalized == "diagonal":
        main = all(is_marked(grid[idx][idx]) for idx in range(5))
        anti = all(is_marked(grid[idx][4 - idx]) for idx in range(5))
        return main or anti

    return False


def _detect_winning_pattern(board: list[int], called_set: set[int]) -> str | None:
    for candidate in ("row", "diagonal"):
        if _board_matches_pattern(board, called_set, candidate):
            return candidate
    return None


def _ensure_cartella_statuses(game: Game) -> dict[str, str]:
    total_cartellas = len(game.cartella_numbers or [])
    statuses: dict[str, str] = {
        str(index): "active" for index in range(total_cartellas)
    }

    if isinstance(game.cartella_statuses, dict):
        for key, value in game.cartella_statuses.items():
            if str(value) in {"active", "banned", "winner"}:
                statuses[str(key)] = str(value)

    for banned_index in game.banned_cartellas or []:
        statuses[str(banned_index)] = "banned"

    for winner_index in game.winners or []:
        statuses[str(winner_index)] = "winner"

    return statuses


def _resolve_game_financials(game: Game) -> tuple[Decimal, Decimal, Decimal]:
    total_pool = (
        game.total_pool
        if game.total_pool and game.total_pool > 0
        else game.bet_amount * Decimal(len(game.cartella_numbers))
    )

    cut_percentage = Decimal(str(game.cut_percentage if game.cut_percentage is not None else Decimal("10")))
    cut_percentage = max(Decimal("0"), min(Decimal("100"), cut_percentage))
    shop_cut = (total_pool * cut_percentage / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    payout_amount = (total_pool - shop_cut).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return total_pool, payout_amount, shop_cut


def _recalculate_session_totals(session: ShopBingoSession) -> tuple[list[int], Decimal]:
    locked_set: set[int] = set()
    total = Decimal("0")

    for player in session.players_data:
        cartellas = player.get("cartella_numbers", []) or []
        locked_set.update(cartellas)

        total_bet = player.get("total_bet")
        if total_bet in (None, ""):
            bet_per_cartella = Decimal(str(player.get("bet_per_cartella", "0") or "0"))
            total += bet_per_cartella * Decimal(len(cartellas))
        else:
            total += Decimal(str(total_bet))

    return sorted(locked_set), total


def _finalize_shop_session(session: ShopBingoSession) -> Game:
    if session.game_id:
        return session.game

    players = session.players_data
    if len(players) != 4:
        raise ValueError("Exactly 4 players are required before game creation")
    if not all(bool(p.get("paid")) for p in players):
        raise ValueError("All 4 players must confirm payment before game creation")

    all_cartella_numbers = [n for p in players for n in p.get("cartella_numbers", [])]
    if len(all_cartella_numbers) > 16:
        raise ValueError("Maximum allowed cartellas is 16")
    if len(set(all_cartella_numbers)) != len(all_cartella_numbers):
        raise ValueError("Duplicate cartella assignment detected")

    cartella_boards = _generate_unique_cartella_boards(len(all_cartella_numbers))
    cartella_map = {str(cartella_number): index for index, cartella_number in enumerate(all_cartella_numbers)}

    feature_flags = session.shop.feature_flags if isinstance(session.shop.feature_flags, dict) else {}
    cut_percentage_raw = feature_flags.get("cut_percentage")
    if cut_percentage_raw is None and "win_percentage" in feature_flags:
        cut_percentage_raw = Decimal("100") - Decimal(str(feature_flags.get("win_percentage", 90)))

    try:
        cut_percentage = Decimal(str(cut_percentage_raw if cut_percentage_raw is not None else 10))
    except Exception:
        cut_percentage = Decimal("10")

    cut_percentage = max(Decimal("0"), min(Decimal("100"), cut_percentage))
    win_percentage = Decimal("100") - cut_percentage
    total_pool = session.total_payable
    if total_pool <= 0:
        raise ValueError("Session total payable must be greater than zero before game creation")

    with db_transaction.atomic():
        game = Game.objects.create(
            shop=session.shop,
            game_mode=Game.Mode.SHOP_FIXED4,
            bet_amount=session.min_bet_per_cartella,
            min_bet_per_cartella=session.min_bet_per_cartella,
            num_players=4,
            win_amount=session.total_payable,
            total_pool=total_pool,
            cut_percentage=cut_percentage,
            win_percentage=win_percentage,
            payout_amount=Decimal("0"),
            shop_cut_amount=Decimal("0"),
            cartella_numbers=cartella_boards,
            cartella_number_map=cartella_map,
            shop_players_data=players,
            status=Game.Status.PENDING,
            called_numbers=[],
            call_cursor=0,
            current_called_number=None,
            started_at=None,
            banned_cartellas=[],
            cartella_statuses={str(index): "active" for index in range(len(cartella_boards))},
            awarded_claims=[],
            winning_pattern="",
        )
        game.bet_debited_at = timezone.now()
        game.save(update_fields=["bet_debited_at"])

        session.status = ShopBingoSession.Status.LOCKED
        session.game = game
        session.save(update_fields=["status", "game", "updated_at"])

    return game


class GameListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: GameSerializer(many=True)}, tags=["Games"])
    def get(self, request):
        games = Game.objects.filter(shop=request.user)
        return Response(GameSerializer(games, many=True).data)

    @extend_schema(request=GameCreateSerializer, responses={201: GameSerializer}, tags=["Games"])
    def post(self, request):
        serializer = GameCreateSerializer(data=request.data, context={"user": request.user})
        serializer.is_valid(raise_exception=True)
        game = serializer.save()
        return Response(GameSerializer(game).data, status=status.HTTP_201_CREATED)


class GameDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_game(self, code, user):
        return get_object_or_404(Game, game_code=code, shop=user)

    @extend_schema(responses={200: GameSerializer, 404: OpenApiResponse(description="Not found")}, tags=["Games"])
    def get(self, request, code: str):
        game = self._get_game(code, request.user)
        return Response(GameSerializer(game).data)


class GameDrawView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: GameSerializer}, tags=["Games"])
    def get(self, request, code: str):
        game = get_object_or_404(Game, game_code=code, shop=request.user)
        data = {
            "game_code": game.game_code,
            "draw_sequence": game.draw_sequence,
            "cartella_draw_sequences": game.cartella_draw_sequences,
        }
        return Response(data)


class GameStateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Games"])
    def get(self, request, code: str):
        game = get_object_or_404(
            Game.objects.only(
                "game_code",
                "status",
                "started_at",
                "call_cursor",
                "current_called_number",
                "called_numbers",
                "cartella_statuses",
            ),
            game_code=code,
            shop=request.user,
        )
        current_number = game.current_called_number
        return Response(
            {
                "game_code": game.game_code,
                "status": game.status,
                "started_at": game.started_at,
                "call_cursor": game.call_cursor,
                "current_called_number": current_number,
                "current_called_formatted": _format_called_number(current_number)
                if current_number
                else None,
                "called_numbers": game.called_numbers,
                "cartella_statuses": game.cartella_statuses,
            }
        )


class GameShuffleView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Games"])
    def post(self, request, code: str):
        game = get_object_or_404(
            Game.objects.only(
                "game_code",
                "status",
                "draw_sequence",
                "called_numbers",
                "call_cursor",
                "current_called_number",
            ),
            game_code=code,
            shop=request.user,
        )

        if game.status != Game.Status.PENDING:
            return Response(
                {"detail": "Shuffle is only allowed before game start"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        game.draw_sequence = random.sample(range(1, 76), 75)
        game.called_numbers = []
        game.call_cursor = 0
        game.current_called_number = None
        game.save(
            update_fields=[
                "draw_sequence",
                "called_numbers",
                "call_cursor",
                "current_called_number",
            ]
        )

        return Response(
            {
                "game_code": game.game_code,
                "status": game.status,
                "message": "Shuffled successfully",
            }
        )


class GameStartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Games"])
    def post(self, request, code: str):
        game = get_object_or_404(
            Game.objects.only("game_code", "status", "started_at"),
            game_code=code,
            shop=request.user,
        )

        if game.status == Game.Status.ACTIVE:
            return Response({"detail": "Game already started"}, status=status.HTTP_200_OK)

        if game.status != Game.Status.PENDING:
            return Response(
                {"detail": "Only pending games can be started"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        game.status = Game.Status.ACTIVE
        game.started_at = timezone.now()
        game.save(update_fields=["status", "started_at"])

        return Response(
            {
                "game_code": game.game_code,
                "status": game.status,
                "started_at": game.started_at,
            }
        )


class GameNextCallView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Games"])
    def post(self, request, code: str):
        game = get_object_or_404(
            Game.objects.only(
                "game_code",
                "status",
                "draw_sequence",
                "called_numbers",
                "call_cursor",
                "current_called_number",
            ),
            game_code=code,
            shop=request.user,
        )

        if game.status != Game.Status.ACTIVE:
            return Response(
                {"detail": "Game must be active before calling numbers"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if game.call_cursor >= len(game.draw_sequence):
            return Response(
                {
                    "game_code": game.game_code,
                    "is_complete": True,
                    "called_numbers": game.called_numbers,
                    "current_called_number": game.current_called_number,
                    "current_called_formatted": _format_called_number(game.current_called_number)
                    if game.current_called_number
                    else None,
                }
            )

        called_numbers = list(game.called_numbers)

        next_number = game.draw_sequence[game.call_cursor]
        called_numbers.append(next_number)
        game.called_numbers = called_numbers
        game.call_cursor += 1
        game.current_called_number = next_number
        game.save(update_fields=["called_numbers", "call_cursor", "current_called_number"])

        return Response(
            {
                "game_code": game.game_code,
                "called_number": next_number,
                "called_formatted": _format_called_number(next_number),
                "called_numbers": game.called_numbers,
                "call_cursor": game.call_cursor,
                "is_complete": game.call_cursor >= len(game.draw_sequence),
            }
        )


class GameCartellaDrawView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        responses={200: OpenApiResponse(description="Cartella draw sequence returned")},
        tags=["Games"],
        summary="Public cartella draw",
    )
    def get(self, request, code: str, cartella_number: int):
        game = get_object_or_404(Game, game_code=code)
        cartella_index = cartella_number - 1
        if cartella_index < 0 or cartella_index >= len(game.cartella_draw_sequences):
            return Response({"detail": "Cartella not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "game_code": game.game_code,
                "cartella_number": cartella_number,
                "cartella_numbers": game.cartella_numbers[cartella_index],
                "cartella_draw_sequence": game.cartella_draw_sequences[cartella_index],
            }
        )


class GameCompleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=GameCompleteSerializer, responses={200: GameSerializer}, tags=["Games"])
    def post(self, request, code: str):
        game = get_object_or_404(Game, game_code=code, shop=request.user)
        serializer = GameCompleteSerializer(game, data=request.data)
        serializer.is_valid(raise_exception=True)
        game = serializer.save()
        return Response(GameSerializer(game).data)


class GameClaimView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=GameClaimSerializer, tags=["Games"])
    def post(self, request, code: str):
        with db_transaction.atomic():
            game = get_object_or_404(Game.objects.select_for_update(), game_code=code, shop=request.user)

            cartella_index = request.data.get("cartella_index")
            pattern_raw = request.data.get("pattern")
            pattern = str(pattern_raw).strip().lower() if pattern_raw is not None else ""

            if game.status != Game.Status.ACTIVE:
                return Response(
                    {"detail": "Claims are only allowed for active games"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                cartella_index = int(cartella_index)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "cartella_index must be an integer"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if cartella_index < 0 or cartella_index >= len(game.cartella_numbers):
                return Response(
                    {"detail": "Cartella index out of range"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if pattern and pattern not in ALLOWED_CLAIM_PATTERNS:
                return Response(
                    {"detail": "pattern must be one of: row, diagonal"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            cartella_statuses = _ensure_cartella_statuses(game)

            banned = set(game.banned_cartellas or [])
            if cartella_index in banned:
                cartella_statuses[str(cartella_index)] = "banned"
                game.cartella_statuses = cartella_statuses
                game.save(update_fields=["cartella_statuses"])
                return Response(
                    {
                        "game_code": game.game_code,
                        "cartella_index": cartella_index,
                        "is_bingo": False,
                        "is_banned": True,
                        "cartella_status": "banned",
                        "cartella_statuses": cartella_statuses,
                        "status": game.status,
                        "detail": "Banned.",
                    },
                    status=status.HTTP_200_OK,
                )

            called_numbers = set(game.called_numbers or [])
            board = game.cartella_numbers[cartella_index]
            detected_pattern = _detect_winning_pattern(board, called_numbers)
            selected_pattern = pattern or detected_pattern or "row"
            is_winner = bool(detected_pattern) if not pattern else _board_matches_pattern(board, called_numbers, pattern)

            claim_log = list(game.awarded_claims or [])
            claim_event = {
                "cartella_index": cartella_index,
                "pattern": selected_pattern,
                "called_count": len(called_numbers),
                "time": timezone.now().isoformat(),
                "result": "win" if is_winner else "false_claim",
            }

            if not is_winner:
                banned.add(cartella_index)
                game.banned_cartellas = sorted(banned)
                cartella_statuses[str(cartella_index)] = "banned"
                game.cartella_statuses = cartella_statuses
                claim_log.append(claim_event)
                game.awarded_claims = claim_log
                game.save(update_fields=["banned_cartellas", "cartella_statuses", "awarded_claims"])

                return Response(
                    {
                        "game_code": game.game_code,
                        "cartella_index": cartella_index,
                        "pattern": selected_pattern,
                        "is_bingo": False,
                        "is_banned": True,
                        "cartella_status": "banned",
                        "cartella_statuses": cartella_statuses,
                        "status": game.status,
                        "called_numbers": game.called_numbers,
                        "detail": "Banned.",
                    },
                    status=status.HTTP_200_OK,
                )

            total_pool, payout_amount, shop_cut = _resolve_game_financials(game)

            if shop_cut > 0:
                apply_transaction(
                    user=game.shop,
                    amount=shop_cut,
                    tx_type=Transaction.Type.BET_CREDIT,
                    reference=f"game:{game.game_code}:shop_cut",
                    metadata={
                        "event": "bingo_shop_cut_credit",
                        "game_id": game.game_code,
                        "total_pool": str(total_pool),
                        "cut_percentage": str(game.cut_percentage),
                        "payout_amount": str(payout_amount),
                        "shop_cut": str(shop_cut),
                        "winner_cartella_index": cartella_index,
                        "pattern": selected_pattern,
                    },
                )

            claim_event.update(
                {
                    "total_pool": str(total_pool),
                    "payout_amount": str(payout_amount),
                    "shop_cut_amount": str(shop_cut),
                }
            )
            claim_log.append(claim_event)

            game.status = Game.Status.COMPLETED
            game.winners = [cartella_index]
            cartella_statuses[str(cartella_index)] = "winner"
            game.cartella_statuses = cartella_statuses
            game.winning_pattern = selected_pattern
            game.total_pool = total_pool
            game.cut_percentage = game.cut_percentage if game.cut_percentage is not None else Decimal("10")
            game.payout_amount = payout_amount
            game.shop_cut_amount = shop_cut
            game.ended_at = game.ended_at or timezone.now()
            game.awarded_claims = claim_log
            game.call_cursor = len(game.draw_sequence)
            game.save(
                update_fields=[
                    "status",
                    "winners",
                    "cartella_statuses",
                    "winning_pattern",
                    "total_pool",
                    "cut_percentage",
                    "payout_amount",
                    "shop_cut_amount",
                    "ended_at",
                    "awarded_claims",
                    "call_cursor",
                ]
            )

            return Response(
                {
                    "game_code": game.game_code,
                    "cartella_index": cartella_index,
                    "pattern": selected_pattern,
                    "is_bingo": True,
                    "is_banned": False,
                    "cartella_status": "winner",
                    "cartella_statuses": cartella_statuses,
                    "status": game.status,
                    "winner": cartella_index,
                    "total_pool": str(total_pool),
                    "payout_amount": str(payout_amount),
                    "shop_cut_amount": str(shop_cut),
                    "detail": "Bingo confirmed. Game completed.",
                },
                status=status.HTTP_200_OK,
            )


class ShopBingoSessionCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=ShopBingoSessionCreateSerializer, responses={201: ShopBingoSessionSerializer}, tags=["Games"])
    def post(self, request):
        serializer = ShopBingoSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session = ShopBingoSession.objects.create(
            shop=request.user,
            fixed_players=4,
            min_bet_per_cartella=serializer.validated_data["min_bet_per_cartella"],
        )
        return Response(ShopBingoSessionSerializer(session).data, status=status.HTTP_201_CREATED)


class ShopBingoSessionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: ShopBingoSessionSerializer}, tags=["Games"])
    def get(self, request, session_id: str):
        session = get_object_or_404(ShopBingoSession, session_id=session_id, shop=request.user)
        return Response(ShopBingoSessionSerializer(session).data)


class ShopBingoSessionReserveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=ShopBingoCartellaSelectSerializer, responses={200: ShopBingoSessionSerializer}, tags=["Games"])
    def post(self, request, session_id: str):
        serializer = ShopBingoCartellaSelectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        player_name = serializer.validated_data["player_name"]
        cartella_numbers = serializer.validated_data["cartella_numbers"]
        bet_per_cartella = serializer.validated_data["bet_per_cartella"]

        with db_transaction.atomic():
            session = get_object_or_404(
                ShopBingoSession.objects.select_for_update(),
                session_id=session_id,
                shop=request.user,
            )

            if session.status != ShopBingoSession.Status.WAITING:
                return Response({"detail": "Session is no longer open"}, status=status.HTTP_400_BAD_REQUEST)
            if bet_per_cartella < session.min_bet_per_cartella:
                return Response({"detail": f"Minimum bet per cartella is {session.min_bet_per_cartella} ETB"}, status=status.HTTP_400_BAD_REQUEST)

            players = list(session.players_data)
            player_index = next(
                (idx for idx, player in enumerate(players) if str(player.get("player_name", "")).lower() == player_name.lower()),
                None,
            )

            if player_index is not None:
                if bool(players[player_index].get("paid", False)):
                    return Response({"detail": "Paid players cannot change cartella selection"}, status=status.HTTP_400_BAD_REQUEST)
            elif len(players) >= session.fixed_players:
                return Response({"detail": "Exactly 4 players are allowed"}, status=status.HTTP_400_BAD_REQUEST)

            taken_by_others = {
                n
                for idx, player in enumerate(players)
                if idx != player_index
                for n in player.get("cartella_numbers", [])
            }
            duplicate_set = set(cartella_numbers).intersection(taken_by_others)
            if duplicate_set:
                return Response(
                    {"detail": f"Cartellas already taken: {sorted(duplicate_set)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            player_total = bet_per_cartella * Decimal(len(cartella_numbers))
            payload = {
                "player_name": player_name,
                "cartella_numbers": cartella_numbers,
                "bet_per_cartella": str(bet_per_cartella),
                "total_bet": str(player_total),
                "paid": False,
                "reserved_at": timezone.now().isoformat(),
            }

            if player_index is None:
                players.append(payload)
            else:
                payload["paid"] = bool(players[player_index].get("paid", False))
                payload["paid_at"] = players[player_index].get("paid_at")
                players[player_index] = payload

            total_cartellas = sum(len(player.get("cartella_numbers", [])) for player in players)
            if total_cartellas > 16:
                return Response({"detail": "Total cartellas cannot exceed 16"}, status=status.HTTP_400_BAD_REQUEST)

            session.players_data = players
            locked, total_payable = _recalculate_session_totals(session)
            session.locked_cartellas = locked
            session.total_payable = total_payable
            session.save(update_fields=["players_data", "locked_cartellas", "total_payable", "updated_at"])

        return Response(ShopBingoSessionSerializer(session).data)


class ShopBingoSessionConfirmPaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=ShopBingoConfirmPaymentSerializer, tags=["Games"])
    def post(self, request, session_id: str):
        serializer = ShopBingoConfirmPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        player_name = serializer.validated_data["player_name"]

        with db_transaction.atomic():
            session = get_object_or_404(
                ShopBingoSession.objects.select_for_update(),
                session_id=session_id,
                shop=request.user,
            )
            players = list(session.players_data)

            player_index = next(
                (idx for idx, player in enumerate(players) if str(player.get("player_name", "")).lower() == player_name.lower()),
                None,
            )
            if player_index is None:
                return Response({"detail": "Player not found in session"}, status=status.HTTP_404_NOT_FOUND)

            if not players[player_index].get("cartella_numbers"):
                return Response({"detail": "Player has no cartellas selected"}, status=status.HTTP_400_BAD_REQUEST)

            players[player_index]["paid"] = True
            players[player_index]["paid_at"] = timezone.now().isoformat()
            session.players_data = players

            locked, total_payable = _recalculate_session_totals(session)
            session.locked_cartellas = locked
            session.total_payable = total_payable
            session.save(update_fields=["players_data", "locked_cartellas", "total_payable", "updated_at"])

            game = None
            if len(players) == session.fixed_players and all(bool(player.get("paid")) for player in players):
                try:
                    game = _finalize_shop_session(session)
                except ValueError as exc:
                    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        response = {
            "session": ShopBingoSessionSerializer(session).data,
            "game_created": bool(game),
        }
        if game:
            response["game"] = GameSerializer(game).data
        return Response(response)


class ShopBingoSessionCreateGameView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Games"])
    def post(self, request, session_id: str):
        with db_transaction.atomic():
            session = get_object_or_404(
                ShopBingoSession.objects.select_for_update(),
                session_id=session_id,
                shop=request.user,
            )

            if session.game_id:
                return Response(
                    {
                        "session": ShopBingoSessionSerializer(session).data,
                        "game_created": True,
                        "game": GameSerializer(session.game).data,
                    }
                )

            players = list(session.players_data)
            if len(players) != session.fixed_players:
                return Response(
                    {
                        "detail": f"Exactly {session.fixed_players} players are required before game creation"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            for idx, player in enumerate(players):
                cartellas = player.get("cartella_numbers") or []
                if not cartellas:
                    return Response(
                        {"detail": f"Player {player.get('player_name') or idx + 1} has no cartellas selected"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if player.get("total_bet") in (None, ""):
                    bet_per_cartella = Decimal(str(player.get("bet_per_cartella", "0") or "0"))
                    players[idx]["total_bet"] = str(bet_per_cartella * Decimal(len(cartellas)))

                if not bool(player.get("paid")):
                    players[idx]["paid"] = True
                    players[idx]["paid_at"] = timezone.now().isoformat()

            session.players_data = players
            locked, total_payable = _recalculate_session_totals(session)
            session.locked_cartellas = locked
            session.total_payable = total_payable
            session.save(update_fields=["players_data", "locked_cartellas", "total_payable", "updated_at"])

            try:
                game = _finalize_shop_session(session)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "session": ShopBingoSessionSerializer(session).data,
                "game_created": True,
                "game": GameSerializer(game).data,
            }
        )


class PublicGameCartellaView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["Games"])
    def get(self, request, game_id: str, cartella_number: int):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        client_ip = (
            x_forwarded_for.split(",")[0].strip()
            if x_forwarded_for
            else request.META.get("REMOTE_ADDR", "unknown")
        )

        rate_limit_count = 30
        rate_limit_window_seconds = 60
        now_ts = timezone.now().timestamp()
        rate_key = f"public-cartella-rate:{client_ip}"
        request_timestamps = cache.get(rate_key, [])
        request_timestamps = [
            ts
            for ts in request_timestamps
            if now_ts - float(ts) < rate_limit_window_seconds
        ]

        if len(request_timestamps) >= rate_limit_count:
            retry_after_seconds = max(
                1,
                math.ceil(
                    rate_limit_window_seconds - (now_ts - float(request_timestamps[0]))
                ),
            )
            return Response(
                {
                    "detail": "Too many requests. Please wait and try again.",
                    "error_code": "rate_limited",
                    "retry_after_seconds": retry_after_seconds,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        request_timestamps.append(now_ts)
        cache.set(rate_key, request_timestamps, timeout=rate_limit_window_seconds)

        game = get_object_or_404(Game, game_code=game_id)

        if game.status != Game.Status.ACTIVE:
            return Response(
                {"detail": "Game is not active"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if game.game_mode == Game.Mode.SHOP_FIXED4:
            mapped_index = game.cartella_number_map.get(str(cartella_number))
            if mapped_index is None:
                return Response({"detail": "Cartella not found"}, status=status.HTTP_404_NOT_FOUND)
            cartella_index = int(mapped_index)
        else:
            cartella_index = cartella_number - 1

        if cartella_index < 0 or cartella_index >= len(game.cartella_numbers):
            return Response({"detail": "Cartella not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            {
                "game_id": game.game_code,
                "cartella_number": cartella_number,
                "cartella_numbers": game.cartella_numbers[cartella_index],
                "cartella_draw_sequence": game.cartella_draw_sequences[cartella_index],
                "status": game.status,
                "called_numbers": game.called_numbers or [],
                "created_at": game.created_at,
            }
        )


class GameAuditReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Games"])
    def get(self, request):
        search = (request.query_params.get("search") or "").strip().lower()
        status_filter = (request.query_params.get("status") or "").strip().lower()
        tx_type_filter = (request.query_params.get("tx_type") or "").strip().lower()
        start_date_raw = (request.query_params.get("start_date") or "").strip()
        end_date_raw = (request.query_params.get("end_date") or "").strip()
        days_raw = (request.query_params.get("days") or "").strip()

        def _range_bounds() -> tuple[datetime | None, datetime | None]:
            start_dt = None
            end_dt = None

            if days_raw:
                try:
                    days_value = int(days_raw)
                except ValueError:
                    days_value = 0

                if days_value > 0:
                    now = timezone.now()
                    start_dt = now - timedelta(days=days_value)
                    end_dt = now
                    return start_dt, end_dt

            if start_date_raw:
                parsed_start = parse_date(start_date_raw)
                if parsed_start:
                    start_dt = timezone.make_aware(
                        datetime.combine(parsed_start, datetime.min.time())
                    )

            if end_date_raw:
                parsed_end = parse_date(end_date_raw)
                if parsed_end:
                    end_dt = timezone.make_aware(
                        datetime.combine(parsed_end, datetime.max.time())
                    )

            if start_dt and end_dt and start_dt > end_dt:
                start_dt, end_dt = end_dt, start_dt

            return start_dt, end_dt

        start_dt, end_dt = _range_bounds()

        games = Game.objects.filter(shop=request.user)
        if status_filter in ALLOWED_GAME_STATUS_FILTERS:
            games = games.filter(status=status_filter)
        if start_dt:
            games = games.filter(created_at__gte=start_dt)
        if end_dt:
            games = games.filter(created_at__lte=end_dt)

        games = games.values(
            "game_code",
            "created_at",
            "ended_at",
            "num_players",
            "total_pool",
            "shop_cut_amount",
            "status",
            "winners",
            "winning_pattern",
            "payout_amount",
            "banned_cartellas",
        ).order_by("-created_at")

        game_history = []
        win_history = []
        banned_list = []

        for game in games.iterator(chunk_size=200):
            winner_indexes = game.get("winners") or []
            winner_labels = [f"Cartella {idx}" for idx in winner_indexes]

            history_item = {
                "game_id": game["game_code"],
                "date": game["created_at"],
                "players": game["num_players"],
                "total_pool": str(game["total_pool"]),
                "winner": winner_labels,
                "shop_cut": str(game["shop_cut_amount"]),
                "status": game["status"],
            }

            if search:
                game_haystack = (
                    f"{history_item['game_id']} {history_item['status']} "
                    f"{' '.join(winner_labels)}"
                ).lower()
                if search not in game_haystack:
                    continue

            game_history.append(history_item)

            if game["status"] == Game.Status.COMPLETED and winner_indexes:
                win_history.append(
                    {
                        "game_id": game["game_code"],
                        "winner_indexes": winner_indexes,
                        "winning_pattern": game["winning_pattern"],
                        "payout_amount": str(game["payout_amount"]),
                        "date": game["ended_at"] or game["created_at"],
                    }
                )

            for banned_idx in game.get("banned_cartellas") or []:
                banned_list.append(
                    {
                        "game_id": game["game_code"],
                        "cartella_index": banned_idx,
                        "status": "banned",
                        "date": game["ended_at"] or game["created_at"],
                    }
                )

        transactions = Transaction.objects.filter(user=request.user)
        if tx_type_filter in ALLOWED_TX_TYPE_FILTERS:
            transactions = transactions.filter(tx_type=tx_type_filter)
        if start_dt:
            transactions = transactions.filter(created_at__gte=start_dt)
        if end_dt:
            transactions = transactions.filter(created_at__lte=end_dt)

        transactions = transactions.values(
            "id",
            "tx_type",
            "amount",
            "balance_before",
            "balance_after",
            "reference",
            "created_at",
            "metadata",
        ).order_by("-created_at")[:300]

        tx_items = []
        for tx in transactions:
            metadata = tx.get("metadata") if isinstance(tx.get("metadata"), dict) else {}
            reference = str(tx.get("reference") or "")
            game_id_from_ref = reference.split(":", 2)[1] if ":" in reference else ""
            item = {
                "id": tx["id"],
                "game_id": metadata.get("game_id") or game_id_from_ref,
                "type": tx["tx_type"],
                "amount": str(tx["amount"]),
                "balance_before": str(tx["balance_before"]),
                "balance_after": str(tx["balance_after"]),
                "reference": reference,
                "created_at": tx["created_at"],
                "metadata": metadata,
            }

            if search:
                tx_haystack = (
                    f"{item['game_id']} {item['type']} {item['reference']}"
                ).lower()
                if search not in tx_haystack:
                    continue

            tx_items.append(item)

        return Response(
            {
                "game_history": game_history,
                "win_history": win_history,
                "banned_cartellas": banned_list,
                "transactions": tx_items,
            }
        )
