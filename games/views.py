from decimal import Decimal
import random

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse
from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from transactions.models import Transaction
from transactions.services import apply_transaction, TransactionError

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


def _generate_cartella_board() -> list[int]:
    numbers: list[int] = []
    ranges = [(1, 15), (16, 30), (31, 45), (46, 60), (61, 75)]
    for min_n, max_n in ranges:
        col = random.sample(range(min_n, max_n + 1), 5)
        numbers.extend(col)
    return numbers


def _recalculate_session_totals(session: ShopBingoSession) -> tuple[list[int], Decimal]:
    locked = sorted({n for p in session.players_data for n in p.get("cartella_numbers", [])})
    total = Decimal("0")
    for player in session.players_data:
        total += Decimal(str(player.get("total_bet", "0")))
    return locked, total


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

    cartella_boards = [_generate_cartella_board() for _ in all_cartella_numbers]
    cartella_map = {str(cartella_number): index for index, cartella_number in enumerate(all_cartella_numbers)}

    with db_transaction.atomic():
        game = Game.objects.create(
            shop=session.shop,
            game_mode=Game.Mode.SHOP_FIXED4,
            bet_amount=session.min_bet_per_cartella,
            min_bet_per_cartella=session.min_bet_per_cartella,
            num_players=4,
            win_amount=session.total_payable,
            cartella_numbers=cartella_boards,
            cartella_number_map=cartella_map,
            shop_players_data=players,
            status=Game.Status.ACTIVE,
            started_at=timezone.now(),
        )

        try:
            apply_transaction(
                user=session.shop,
                amount=session.total_payable,
                tx_type=Transaction.Type.BET_DEBIT,
                reference=f"game:{game.game_code}:shop_lobby_bet",
                metadata={
                    "event": "shop_mode_bet_debit",
                    "session_id": session.session_id,
                    "players": players,
                    "cartella_count": len(all_cartella_numbers),
                    "min_bet_per_cartella": str(session.min_bet_per_cartella),
                },
            )
        except TransactionError as exc:
            raise ValueError(str(exc)) from exc

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
        game = get_object_or_404(Game, game_code=code, shop=request.user)
        serializer = GameClaimSerializer(data=request.data, context={"game": game})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(
            {
                "game_code": game.game_code,
                "cartella_index": data["cartella_index"],
                "is_bingo": data["is_bingo"],
                "matched_count": data["matched_count"],
                "required_count": data["required_count"],
                "missing_numbers": data["missing_numbers"],
            }
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
            session = ShopBingoSession.objects.select_for_update().get(session_id=session_id, shop=request.user)

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
            duplicates = [n for n in cartella_numbers if n in taken_by_others]
            if duplicates:
                return Response({"detail": f"Cartellas already taken: {sorted(set(duplicates))}"}, status=status.HTTP_400_BAD_REQUEST)

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
            session = ShopBingoSession.objects.select_for_update().get(session_id=session_id, shop=request.user)
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


class PublicGameCartellaView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["Games"])
    def get(self, request, game_id: str, cartella_number: int):
        game = get_object_or_404(Game, game_code=game_id)

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
                "created_at": game.created_at,
            }
        )
