import random
from typing import List

from rest_framework import serializers

from accounts.models import ShopUser
from .models import Game


class GameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Game
        fields = [
            "id",
            "game_code",
            "bet_amount",
            "num_players",
            "win_amount",
            "cartella_numbers",
            "cartella_draw_sequences",
            "draw_sequence",
            "status",
            "winners",
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
        game = Game.objects.create(
            shop=user,
            bet_amount=validated_data["bet_amount"],
            num_players=validated_data["num_players"],
            win_amount=validated_data["win_amount"],
            cartella_numbers=cartellas,
        )
        # draw sequences generated in model save
        game.save()
        return game


class GameCompleteSerializer(serializers.ModelSerializer):
    winners = serializers.ListField(child=serializers.IntegerField(), required=False, allow_empty=True)
    status = serializers.ChoiceField(choices=[Game.Status.COMPLETED, Game.Status.CANCELLED])

    class Meta:
        model = Game
        fields = ["status", "winners"]

    def update(self, instance: Game, validated_data):
        instance.status = validated_data.get("status", instance.status)
        instance.winners = validated_data.get("winners", [])
        instance.ended_at = instance.ended_at or instance.created_at
        instance.save(update_fields=["status", "winners", "ended_at"])
        return instance
