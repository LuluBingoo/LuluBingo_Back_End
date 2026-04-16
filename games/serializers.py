import random
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.models import ShopUser
from .models import Game, ShopBingoSession
from transactions.models import Transaction
from transactions.services import apply_transaction


def _normalize_cartella_board(board: list[int] | tuple[int, ...] | None) -> list[int] | None:
    if not isinstance(board, (list, tuple)):
        return None

    normalized = list(board[:25])
    if len(normalized) < 25:
        return None

    normalized[12] = 0
    return normalized


def _resolve_game_financials(game: Game) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    total_pool = (
        game.total_pool
        if game.total_pool and game.total_pool > 0
        else game.bet_amount * Decimal(len(game.cartella_numbers))
    )

    cut_percentage = Decimal(str(game.cut_percentage if game.cut_percentage is not None else Decimal("10")))
    cut_percentage = max(Decimal("0"), min(Decimal("100"), cut_percentage))

    lulu_cut_percentage = Decimal(
        str(
            game.lulu_cut_percentage
            if game.lulu_cut_percentage is not None
            else getattr(game.shop, "lulu_cut_percentage", Decimal("15"))
        )
    )
    lulu_cut_percentage = max(Decimal("0"), min(Decimal("100"), lulu_cut_percentage))

    shop_cut = (total_pool * cut_percentage / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    lulu_cut = (shop_cut * lulu_cut_percentage / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    shop_net_cut = (shop_cut - lulu_cut).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    payout_amount = (total_pool - shop_cut).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return total_pool, payout_amount, shop_cut, lulu_cut, shop_net_cut


class GameSerializer(serializers.ModelSerializer):
    assigned_cartella_numbers = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = [
            "id",
            "game_code",
            "game_mode",
            "bet_amount",
            "min_bet_per_cartella",
            "num_players",
            "win_amount",
            "cartella_numbers",
            "assigned_cartella_numbers",
            "cartella_number_map",
            "cartella_draw_sequences",
            "draw_sequence",
            "called_numbers",
            "call_cursor",
            "current_called_number",
            "shop_players_data",
            "status",
            "winners",
            "banned_cartellas",
            "cartella_statuses",
            "awarded_claims",
            "total_pool",
            "cut_percentage",
            "lulu_cut_percentage",
            "win_percentage",
            "payout_amount",
            "shop_cut_amount",
            "lulu_cut_amount",
            "shop_net_cut_amount",
            "winning_pattern",
            "created_at",
            "started_at",
            "ended_at",
        ]
        read_only_fields = fields

    def get_assigned_cartella_numbers(self, obj: Game) -> list[int]:
        if isinstance(obj.cartella_number_map, dict) and obj.cartella_number_map:
            ordered = sorted(
                ((int(number), int(index)) for number, index in obj.cartella_number_map.items()),
                key=lambda item: item[1],
            )
            return [number for number, _ in ordered]
        return list(range(1, len(obj.cartella_numbers or []) + 1))


class GameCreateSerializer(serializers.ModelSerializer):
    cartella_numbers = serializers.ListField(child=serializers.ListField(child=serializers.IntegerField()), allow_empty=False)

    class Meta:
        model = Game
        fields = ["bet_amount", "num_players", "win_amount", "cartella_numbers"]

    def validate_cartella_numbers(self, value: List[List[int]]):
        if not value:
            raise serializers.ValidationError("Provide at least one cartella")
        flat_len = sum(len(c) for c in value)
        if flat_len == 0:
            raise serializers.ValidationError("Cartella numbers cannot be empty")
        for cartella in value:
            for n in cartella:
                if n < 1 or n > 75:
                    raise serializers.ValidationError("Cartella numbers must be between 1 and 75")
        return value

    def validate(self, attrs):
        num_players = attrs.get("num_players") or 0
        cartellas = attrs.get("cartella_numbers", [])
        max_cartellas = num_players * 4 if num_players else len(cartellas)
        if len(cartellas) > max_cartellas:
            raise serializers.ValidationError({"cartella_numbers": "Total cartellas exceed allowed 4 per player"})
        return attrs

    def create(self, validated_data):
        user: ShopUser = self.context["user"]
        cartellas = validated_data["cartella_numbers"]
        total_bet = validated_data["bet_amount"] * len(cartellas)

        cut_percentage_raw = getattr(user, "shop_cut_percentage", Decimal("10"))
        lulu_cut_percentage_raw = getattr(user, "lulu_cut_percentage", Decimal("15"))
        try:
            cut_percentage = Decimal(str(cut_percentage_raw))
        except Exception:
            cut_percentage = Decimal("10")
        try:
            lulu_cut_percentage = Decimal(str(lulu_cut_percentage_raw))
        except Exception:
            lulu_cut_percentage = Decimal("15")

        cut_percentage = max(Decimal("0"), min(Decimal("100"), cut_percentage))
        lulu_cut_percentage = max(Decimal("0"), min(Decimal("100"), lulu_cut_percentage))

        estimated_shop_cut = (total_bet * cut_percentage / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        estimated_lulu_cut = (estimated_shop_cut * lulu_cut_percentage / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        if Decimal(str(user.wallet_balance)) < estimated_lulu_cut:
            raise serializers.ValidationError(
                {
                    "detail": "Insufficient balance to cover Lulu cut for this game.",
                    "error_code": "insufficient_lulu_cut_balance",
                    "required_lulu_cut": str(estimated_lulu_cut),
                    "current_balance": str(user.wallet_balance),
                    "estimated_shop_cut": str(estimated_shop_cut),
                }
            )

        win_percentage = Decimal("100") - cut_percentage

        with db_transaction.atomic():
            game = Game.objects.create(
                shop=user,
                bet_amount=validated_data["bet_amount"],
                num_players=validated_data["num_players"],
                win_amount=validated_data["win_amount"],
                total_pool=total_bet,
                cut_percentage=cut_percentage,
                lulu_cut_percentage=lulu_cut_percentage,
                win_percentage=win_percentage,
                cartella_numbers=cartellas,
                cartella_statuses={str(index): "active" for index in range(len(cartellas))},
                status=Game.Status.ACTIVE,
                started_at=timezone.now(),
            )

        return game


class GameCompleteSerializer(serializers.ModelSerializer):
    winners = serializers.ListField(child=serializers.IntegerField(), required=False, allow_empty=True)
    status = serializers.ChoiceField(choices=[Game.Status.COMPLETED, Game.Status.CANCELLED])

    class Meta:
        model = Game
        fields = ["status", "winners"]

    def validate(self, attrs):
        status_value = attrs.get("status")
        winners = attrs.get("winners", [])
        game: Game = self.instance

        if game.status in {Game.Status.COMPLETED, Game.Status.CANCELLED}:
            raise serializers.ValidationError("Game is already finalized")

        if status_value == Game.Status.COMPLETED:
            if not winners:
                raise serializers.ValidationError({"winners": "At least one winner is required for completed games"})
            cartella_count = len(game.cartella_numbers)
            invalid_indexes = [winner for winner in winners if winner < 0 or winner >= cartella_count]
            if invalid_indexes:
                raise serializers.ValidationError({"winners": "Winner indexes out of range"})

        return attrs

    def update(self, instance: Game, validated_data):
        status_value = validated_data.get("status", instance.status)
        winners = validated_data.get("winners", [])

        with db_transaction.atomic():
            if status_value == Game.Status.COMPLETED and instance.payout_credited_at is None:
                total_pool, payout_amount, shop_cut, lulu_cut, shop_net_cut = _resolve_game_financials(instance)

                if lulu_cut > 0:
                    apply_transaction(
                        user=instance.shop,
                        amount=lulu_cut,
                        tx_type=Transaction.Type.LULU_CUT_DEBIT,
                        reference=f"game:{instance.game_code}:lulu_cut",
                        metadata={
                            "event": "game_lulu_cut_debit",
                            "game_code": instance.game_code,
                            "total_pool": str(total_pool),
                            "shop_cut": str(shop_cut),
                            "lulu_cut": str(lulu_cut),
                            "shop_net_cut": str(shop_net_cut),
                            "winners": winners,
                        },
                    )

                instance.total_pool = total_pool
                instance.payout_amount = payout_amount
                instance.shop_cut_amount = shop_cut
                instance.lulu_cut_amount = lulu_cut
                instance.shop_net_cut_amount = shop_net_cut
                instance.payout_credited_at = timezone.now()

            instance.status = status_value
            instance.winners = winners
            instance.ended_at = instance.ended_at or timezone.now()
            instance.save(
                update_fields=[
                    "status",
                    "winners",
                    "ended_at",
                    "total_pool",
                    "payout_amount",
                    "shop_cut_amount",
                    "lulu_cut_amount",
                    "shop_net_cut_amount",
                    "payout_credited_at",
                    "refund_credited_at",
                ]
            )
        return instance


class GameClaimSerializer(serializers.Serializer):
    cartella_index = serializers.IntegerField(min_value=0)
    called_numbers = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=75),
        allow_empty=False,
        required=False,
    )
    pattern = serializers.ChoiceField(choices=[("row", "row"), ("diagonal", "diagonal")], required=False)
    ban_on_false_claim = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        game: Game = self.context["game"]
        cartella_index = attrs["cartella_index"]

        called_numbers = attrs.get("called_numbers")
        if called_numbers is None:
            return attrs

        if game.status != Game.Status.ACTIVE:
            raise serializers.ValidationError("Claims are only allowed for active games")

        if cartella_index >= len(game.cartella_numbers):
            raise serializers.ValidationError({"cartella_index": "Cartella index out of range"})

        called_set = set(called_numbers)
        cartella_numbers = _normalize_cartella_board(game.cartella_numbers[cartella_index])
        if cartella_numbers is None:
            raise serializers.ValidationError({"cartella_index": "Cartella board data is invalid"})

        winning_numbers = [number for index, number in enumerate(cartella_numbers) if index != 12]

        missing_numbers = [number for number in winning_numbers if number not in called_set]
        attrs["is_bingo"] = len(missing_numbers) == 0
        attrs["missing_numbers"] = missing_numbers
        attrs["matched_count"] = len(winning_numbers) - len(missing_numbers)
        attrs["required_count"] = len(winning_numbers)
        return attrs


class ShopBingoSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopBingoSession
        fields = [
            "session_id",
            "status",
            "play_mode",
            "fixed_players",
            "min_bet_per_cartella",
            "players_data",
            "locked_cartellas",
            "total_payable",
            "created_at",
            "updated_at",
            "game",
        ]


class ShopBingoSessionCreateSerializer(serializers.Serializer):
    min_bet_per_cartella = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    fixed_players = serializers.IntegerField(required=False, min_value=2, default=4)
    play_mode = serializers.ChoiceField(choices=ShopBingoSession.PlayMode.choices, required=False, default=ShopBingoSession.PlayMode.OFFLINE)

    def validate_min_bet_per_cartella(self, value: Decimal):
        if value < Decimal("10.00"):
            raise serializers.ValidationError("Minimum bet per cartella is 10 ETB")
        return value


class ShopBingoCartellaSelectSerializer(serializers.Serializer):
    player_name = serializers.CharField(max_length=80)
    cartella_numbers = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=200),
        allow_empty=True,
    )
    bet_per_cartella = serializers.DecimalField(max_digits=12, decimal_places=2)

    def validate_player_name(self, value: str):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Player name is required")
        return cleaned

    def validate_cartella_numbers(self, value: list[int]):
        if len(value) > 4:
            raise serializers.ValidationError("A player can select at most 4 cartellas")
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Duplicate cartellas are not allowed")
        return value

    def validate_bet_per_cartella(self, value: Decimal):
        if value < Decimal("10.00"):
            raise serializers.ValidationError("Minimum bet per cartella is 10 ETB")
        return value


class ShopBingoConfirmPaymentSerializer(serializers.Serializer):
    player_name = serializers.CharField(max_length=80)

    def validate_player_name(self, value: str):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Player name is required")
        return cleaned


class DetailResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()


class GameStateResponseSerializer(serializers.Serializer):
    game_code = serializers.CharField()
    status = serializers.ChoiceField(choices=Game.Status.choices)
    started_at = serializers.DateTimeField(allow_null=True)
    call_cursor = serializers.IntegerField()
    current_called_number = serializers.IntegerField(allow_null=True)
    current_called_formatted = serializers.CharField(allow_null=True)
    called_numbers = serializers.ListField(child=serializers.IntegerField())
    cartella_statuses = serializers.DictField(child=serializers.CharField(), required=False)


class GameShuffleResponseSerializer(serializers.Serializer):
    game_code = serializers.CharField()
    status = serializers.ChoiceField(choices=Game.Status.choices)
    message = serializers.CharField()


class GameStartResponseSerializer(serializers.Serializer):
    game_code = serializers.CharField()
    status = serializers.ChoiceField(choices=Game.Status.choices)
    started_at = serializers.DateTimeField(allow_null=True)


class GameNextCallResponseSerializer(serializers.Serializer):
    game_code = serializers.CharField()
    called_number = serializers.IntegerField(required=False)
    called_formatted = serializers.CharField(required=False)
    called_numbers = serializers.ListField(child=serializers.IntegerField())
    call_cursor = serializers.IntegerField(required=False)
    current_called_number = serializers.IntegerField(required=False, allow_null=True)
    current_called_formatted = serializers.CharField(required=False, allow_null=True)
    is_complete = serializers.BooleanField()


class GameCartellaDrawResponseSerializer(serializers.Serializer):
    game_code = serializers.CharField()
    cartella_number = serializers.IntegerField()
    cartella_numbers = serializers.ListField(child=serializers.IntegerField())
    cartella_draw_sequence = serializers.ListField(child=serializers.IntegerField())


class PublicCartellaLookupSerializer(serializers.Serializer):
    game_id = serializers.CharField()
    cartella_numbers = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=4,
        help_text="Up to 4 cartella numbers for the given game.",
    )

    def validate_game_id(self, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise serializers.ValidationError("Game ID is required.")
        return normalized

    def validate_cartella_numbers(self, value: list[int]) -> list[int]:
        normalized: list[int] = []
        seen: set[int] = set()
        for number in value:
            if number in seen:
                continue
            seen.add(number)
            normalized.append(number)
        return normalized


class GameClaimResponseSerializer(serializers.Serializer):
    game_code = serializers.CharField()
    cartella_index = serializers.IntegerField()
    pattern = serializers.CharField(required=False)
    is_bingo = serializers.BooleanField()
    is_banned = serializers.BooleanField(required=False)
    would_ban = serializers.BooleanField(required=False)
    cartella_status = serializers.CharField(required=False)
    cartella_statuses = serializers.DictField(child=serializers.CharField(), required=False)
    status = serializers.ChoiceField(choices=Game.Status.choices, required=False)
    winner = serializers.IntegerField(required=False)
    total_pool = serializers.CharField(required=False)
    payout_amount = serializers.CharField(required=False)
    shop_cut_amount = serializers.CharField(required=False)
    lulu_cut_amount = serializers.CharField(required=False)
    shop_net_cut_amount = serializers.CharField(required=False)
    called_numbers = serializers.ListField(child=serializers.IntegerField(), required=False)
    detail = serializers.CharField(required=False)


class ShopBingoSessionGameResponseSerializer(serializers.Serializer):
    session = ShopBingoSessionSerializer()
    game_created = serializers.BooleanField()
    game = GameSerializer(required=False)


class PublicCartellaItemSerializer(serializers.Serializer):
    cartella_number = serializers.IntegerField()
    cartella_numbers = serializers.ListField(child=serializers.IntegerField())
    cartella_draw_sequence = serializers.ListField(child=serializers.IntegerField())


class PublicCartellaResponseSerializer(serializers.Serializer):
    game_id = serializers.CharField()
    requested_cartella_numbers = serializers.ListField(child=serializers.IntegerField())
    missing_cartella_numbers = serializers.ListField(child=serializers.IntegerField())
    cartellas = PublicCartellaItemSerializer(many=True)
    status = serializers.ChoiceField(choices=Game.Status.choices)
    called_numbers = serializers.ListField(child=serializers.IntegerField())
    created_at = serializers.DateTimeField()


class GameHistoryItemSerializer(serializers.Serializer):
    game_id = serializers.CharField()
    date = serializers.DateTimeField()
    players = serializers.IntegerField()
    total_pool = serializers.CharField()
    winner = serializers.ListField(child=serializers.CharField())
    shop_cut = serializers.CharField()
    lulu_cut = serializers.CharField(required=False)
    shop_net_cut = serializers.CharField(required=False)
    status = serializers.ChoiceField(choices=Game.Status.choices)


class WinHistoryItemSerializer(serializers.Serializer):
    game_id = serializers.CharField()
    winner_indexes = serializers.ListField(child=serializers.IntegerField())
    winning_pattern = serializers.CharField(allow_blank=True, allow_null=True)
    payout_amount = serializers.CharField()
    date = serializers.DateTimeField()


class BannedCartellaItemSerializer(serializers.Serializer):
    game_id = serializers.CharField()
    cartella_index = serializers.IntegerField()
    status = serializers.CharField()
    date = serializers.DateTimeField()


class ReportTransactionItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    game_id = serializers.CharField(allow_blank=True, allow_null=True)
    type = serializers.CharField()
    amount = serializers.CharField()
    balance_before = serializers.CharField()
    balance_after = serializers.CharField()
    reference = serializers.CharField()
    created_at = serializers.DateTimeField()
    metadata = serializers.DictField(required=False)


class GameAuditReportResponseSerializer(serializers.Serializer):
    game_history = GameHistoryItemSerializer(many=True)
    win_history = WinHistoryItemSerializer(many=True)
    banned_cartellas = BannedCartellaItemSerializer(many=True)
    transactions = ReportTransactionItemSerializer(many=True)
