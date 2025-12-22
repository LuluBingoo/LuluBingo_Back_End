from django.contrib.auth import authenticate
from rest_framework import serializers

from .models import LoginAttempt, ShopUser


class ShopUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopUser
        fields = ["id", "username", "created_at", "is_active", "is_staff"]


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        username = attrs.get("username")
        password = attrs.get("password")
        request = self.context.get("request")
        user = authenticate(request=request, username=username, password=password)
        if not user:
            raise serializers.ValidationError("Invalid credentials")
        attrs["user"] = user
        return attrs


class LoginAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginAttempt
        fields = ["id", "username", "ip_address", "success", "timestamp", "user_agent"]
