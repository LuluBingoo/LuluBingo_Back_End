from django.contrib.auth import authenticate
from rest_framework import serializers

from .models import LoginAttempt, ShopUser


class ShopUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopUser
        fields = [
            "id",
            "username",
            "name",
            "status",
            "contact_phone",
            "contact_email",
            "wallet_balance",
            "commission_rate",
            "max_stake",
            "feature_flags",
            "must_change_password",
            "created_at",
        ]


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        username = attrs.get("username")
        password = attrs.get("password")
        request = self.context.get("request")
        user = authenticate(request=request, username=username, password=password)
        if not user:
            try:
                shop = ShopUser.objects.get(username=username)
            except ShopUser.DoesNotExist:
                raise serializers.ValidationError("Invalid credentials")
            if shop.status != ShopUser.Status.ACTIVE:
                raise serializers.ValidationError("Shop is not active. Contact support.")
            raise serializers.ValidationError("Invalid credentials")
        attrs["user"] = user
        return attrs


class LoginAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginAttempt
        fields = ["id", "username", "ip_address", "success", "timestamp", "user_agent"]


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        if value.strip() == "":
            raise serializers.ValidationError("New password cannot be blank.")
        return value


class AuthTokenResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    requires_password_change = serializers.BooleanField()
    user = ShopUserSerializer(read_only=True)


class MeResponseSerializer(serializers.Serializer):
    user = ShopUserSerializer(read_only=True)
