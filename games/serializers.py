import random
from decimal import Decimal
from typing import List

from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.models import ShopUser
from .models import Game, ShopBingoSession
from transactions.models import Transaction
from transactions.services import TransactionError, apply_transaction


class GameSerializer(serializers.ModelSerializer):
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
            "win_percentage",
            "payout_amount",
            "shop_cut_amount",
            "winning_pattern",
            "created_at",
            "started_at",
            "ended_at",
        ]
        read_only_fields = fields


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
        feature_flags = user.feature_flags if isinstance(user.feature_flags, dict) else {}

        cut_percentage_raw = feature_flags.get("cut_percentage", 10)
        try:
            cut_percentage = Decimal(str(cut_percentage_raw))
        except Exception:
            cut_percentage = Decimal("10")
        cut_percentage = max(Decimal("0"), min(Decimal("100"), cut_percentage))
        win_percentage = Decimal("100") - cut_percentage

        try:
            with db_transaction.atomic():
                game = Game.objects.create(
                    shop=user,
                    bet_amount=validated_data["bet_amount"],
                    num_players=validated_data["num_players"],
                    win_amount=validated_data["win_amount"],
                    total_pool=total_bet,
                    cut_percentage=cut_percentage,
                    win_percentage=win_percentage,
                    cartella_numbers=cartellas,
                    cartella_statuses={str(index): "active" for index in range(len(cartellas))},
                    status=Game.Status.ACTIVE,
                    started_at=timezone.now(),
                )
                apply_transaction(
                    user=user,
                    amount=total_bet,
                    tx_type=Transaction.Type.BET_DEBIT,
                    reference=f"game:{game.game_code}:bet",
                    metadata={
                        "event": "game_bet_debit",
                        "game_code": game.game_code,
                        "cartella_count": len(cartellas),
                        "bet_per_cartella": str(validated_data["bet_amount"]),
                    },
                )
                game.bet_debited_at = timezone.now()
                game.save(update_fields=["bet_debited_at"])
        except TransactionError as exc:
            raise serializers.ValidationError({"bet_amount": str(exc)}) from exc

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
        cartella_count = len(instance.cartella_numbers)
        total_bet = instance.bet_amount * cartella_count

        with db_transaction.atomic():
            if status_value == Game.Status.COMPLETED and instance.payout_credited_at is None:
                payout_amount = instance.win_amount * len(winners)
                if payout_amount > 0:
                    apply_transaction(
                        user=instance.shop,
                        amount=payout_amount,
                        tx_type=Transaction.Type.BET_CREDIT,
                        reference=f"game:{instance.game_code}:payout",
                        metadata={
                            "event": "game_payout_credit",
                            "game_code": instance.game_code,
                            "winners": winners,
                            "win_amount_per_winner": str(instance.win_amount),
                        },
                    )
                instance.payout_credited_at = timezone.now()

            if status_value == Game.Status.CANCELLED and instance.refund_credited_at is None and instance.bet_debited_at:
                apply_transaction(
                    user=instance.shop,
                    amount=total_bet,
                    tx_type=Transaction.Type.BET_CREDIT,
                    reference=f"game:{instance.game_code}:refund",
                    metadata={
                        "event": "game_refund_credit",
                        "game_code": instance.game_code,
                        "cartella_count": cartella_count,
                        "bet_per_cartella": str(instance.bet_amount),
                    },
                )
                instance.refund_credited_at = timezone.now()

            instance.status = status_value
            instance.winners = winners
            instance.ended_at = instance.ended_at or timezone.now()
            instance.save(
                update_fields=[
                    "status",
                    "winners",
                    "ended_at",
                    "payout_credited_at",
                    "refund_credited_at",
                ]
            )
        return instance


class GameClaimSerializer(serializers.Serializer):
    cartella_index = serializers.IntegerField(min_value=0)
    called_numbers = serializers.ListField(child=serializers.IntegerField(min_value=1, max_value=75), allow_empty=False)

    def validate(self, attrs):
        game: Game = self.context["game"]
        cartella_index = attrs["cartella_index"]
        called_numbers = attrs["called_numbers"]

        if game.status != Game.Status.ACTIVE:
            raise serializers.ValidationError("Claims are only allowed for active games")

        if cartella_index >= len(game.cartella_numbers):
            raise serializers.ValidationError({"cartella_index": "Cartella index out of range"})

        called_set = set(called_numbers)
        cartella_numbers = game.cartella_numbers[cartella_index]
        if len(cartella_numbers) == 25:
            winning_numbers = [number for index, number in enumerate(cartella_numbers) if index != 12]
        else:
            winning_numbers = list(cartella_numbers)

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
    min_bet_per_cartella = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("20.00"))

    def validate_min_bet_per_cartella(self, value: Decimal):
        if value < Decimal("20.00"):
            raise serializers.ValidationError("Minimum bet per cartella is 20 ETB")
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
        if value < Decimal("20.00"):
            raise serializers.ValidationError("Minimum bet per cartella is 20 ETB")
        return value


class ShopBingoConfirmPaymentSerializer(serializers.Serializer):
    player_name = serializers.CharField(max_length=80)

    def validate_player_name(self, value: str):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Player name is required")
        return cleaned
