from decimal import Decimal

from django.db import transaction as db_transaction
from rest_framework import serializers

from games.models import Game
from transactions.models import Transaction
from transactions.services import apply_transaction

from .models import ShopUser


def _normalize_percentage(value: Decimal, field_label: str) -> Decimal:
    normalized = Decimal(str(value))
    if normalized < Decimal("0") or normalized > Decimal("100"):
        raise serializers.ValidationError(f"{field_label} must be between 0 and 100.")
    return normalized


class ManagerCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = ShopUser
        fields = [
            "username",
            "password",
            "name",
            "contact_phone",
            "contact_email",
            "status",
            "must_change_password",
        ]
        extra_kwargs = {
            "status": {"required": False},
            "must_change_password": {"required": False},
        }

    def validate_status(self, value: str) -> str:
        if value == ShopUser.Status.PENDING:
            raise serializers.ValidationError("Managers cannot be created with pending status.")
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data.setdefault("status", ShopUser.Status.ACTIVE)
        validated_data.setdefault("must_change_password", False)
        return ShopUser.objects.create_user(
            password=password,
            role=ShopUser.Role.MANAGER,
            is_staff=True,
            **validated_data,
        )


class ManagerUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, required=False)

    class Meta:
        model = ShopUser
        fields = [
            "name",
            "contact_phone",
            "contact_email",
            "status",
            "must_change_password",
            "password",
        ]

    def validate_status(self, value: str) -> str:
        if value == ShopUser.Status.PENDING:
            raise serializers.ValidationError("Managers cannot have pending status.")
        return value

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.role = ShopUser.Role.MANAGER
        instance.is_staff = True
        instance.save()
        return instance


class AdminShopCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    initial_balance = serializers.DecimalField(max_digits=12, decimal_places=2, write_only=True)

    class Meta:
        model = ShopUser
        fields = [
            "username",
            "password",
            "name",
            "contact_phone",
            "contact_email",
            "status",
            "must_change_password",
            "shop_cut_percentage",
            "lulu_cut_percentage",
            "max_stake",
            "feature_flags",
            "bank_name",
            "bank_account_name",
            "bank_account_number",
            "initial_balance",
        ]
        extra_kwargs = {
            "status": {"required": False},
            "must_change_password": {"required": False},
            "feature_flags": {"required": False},
            "bank_name": {"required": False, "allow_blank": True},
            "bank_account_name": {"required": False, "allow_blank": True},
            "bank_account_number": {"required": False, "allow_blank": True},
            "max_stake": {"required": False},
        }

    def validate_shop_cut_percentage(self, value: Decimal) -> Decimal:
        return _normalize_percentage(value, "Shop cut percentage")

    def validate_lulu_cut_percentage(self, value: Decimal) -> Decimal:
        return _normalize_percentage(value, "Lulu cut percentage")

    def validate_initial_balance(self, value: Decimal) -> Decimal:
        if value <= Decimal("0"):
            raise serializers.ValidationError("Initial balance must be greater than 0.")
        return value

    def create(self, validated_data):
        initial_balance = validated_data.pop("initial_balance")
        password = validated_data.pop("password")
        validated_data.setdefault("status", ShopUser.Status.ACTIVE)
        validated_data.setdefault("must_change_password", True)

        request = self.context.get("request")
        creator = getattr(request, "user", None)

        with db_transaction.atomic():
            shop = ShopUser.objects.create_user(
                password=password,
                role=ShopUser.Role.SHOP,
                is_staff=False,
                **validated_data,
            )

            initial_tx = apply_transaction(
                user=shop,
                amount=initial_balance,
                tx_type=Transaction.Type.DEPOSIT,
                reference=f"shop:{shop.shop_code}:initial_money",
                metadata={
                    "event": "shop_creation_initial_money",
                    "shop_id": shop.id,
                    "shop_code": shop.shop_code,
                    "shop_username": shop.username,
                    "created_by_user_id": getattr(creator, "id", None),
                    "created_by_username": getattr(creator, "username", ""),
                },
                actor_role=Transaction.ActorRole.ADMIN,
                operation_source=Transaction.OperationSource.ADMIN,
            )

        shop._initial_funding_tx = initial_tx
        return shop


class AdminShopUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, required=False)

    class Meta:
        model = ShopUser
        fields = [
            "name",
            "contact_phone",
            "contact_email",
            "status",
            "must_change_password",
            "shop_cut_percentage",
            "lulu_cut_percentage",
            "max_stake",
            "feature_flags",
            "bank_name",
            "bank_account_name",
            "bank_account_number",
            "password",
        ]

    def validate_shop_cut_percentage(self, value: Decimal) -> Decimal:
        return _normalize_percentage(value, "Shop cut percentage")

    def validate_lulu_cut_percentage(self, value: Decimal) -> Decimal:
        return _normalize_percentage(value, "Lulu cut percentage")

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.role = ShopUser.Role.SHOP
        instance.is_staff = False
        instance.save()
        return instance


class AdminShopBalanceTopUpSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def validate_amount(self, value: Decimal) -> Decimal:
        if value <= Decimal("0"):
            raise serializers.ValidationError("Amount must be greater than 0.")
        return value


class AdminShopBalanceDeductSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reason = serializers.CharField(max_length=240)
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def validate_amount(self, value: Decimal) -> Decimal:
        if value <= Decimal("0"):
            raise serializers.ValidationError("Amount must be greater than 0.")
        return value

    def validate_reason(self, value: str) -> str:
        reason = value.strip()
        if not reason:
            raise serializers.ValidationError("Reason is required.")
        return reason


class AdminGameListSerializer(serializers.ModelSerializer):
    shop_id = serializers.IntegerField(source="shop.id", read_only=True)
    shop_username = serializers.CharField(source="shop.username", read_only=True)
    shop_name = serializers.CharField(source="shop.name", read_only=True)

    class Meta:
        model = Game
        fields = [
            "id",
            "game_code",
            "game_mode",
            "status",
            "shop_id",
            "shop_username",
            "shop_name",
            "total_pool",
            "cut_percentage",
            "lulu_cut_percentage",
            "payout_amount",
            "shop_cut_amount",
            "lulu_cut_amount",
            "shop_net_cut_amount",
            "winning_pattern",
            "created_at",
            "started_at",
            "ended_at",
        ]


class AdminTransactionListSerializer(serializers.ModelSerializer):
    shop_id = serializers.IntegerField(source="user.id", read_only=True)
    shop_username = serializers.CharField(source="user.username", read_only=True)
    shop_name = serializers.CharField(source="user.name", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id",
            "shop_id",
            "shop_username",
            "shop_name",
            "tx_type",
            "amount",
            "balance_before",
            "balance_after",
            "reference",
            "metadata",
            "actor_role",
            "operation_source",
            "currency",
            "created_at",
        ]
