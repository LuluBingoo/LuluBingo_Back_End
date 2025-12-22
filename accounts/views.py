from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import LoginAttempt
from .serializers import (
    AuthTokenResponseSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    MeResponseSerializer,
    ShopUserSerializer,
)


def _get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _record_attempt(username: str, success: bool, request, user=None):
    LoginAttempt.objects.create(
        username=username,
        success=success,
        ip_address=_get_client_ip(request),
        user=user if success else None,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:512],
        timestamp=timezone.now(),
    )


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=LoginSerializer,
        responses={
            200: AuthTokenResponseSerializer,
            400: OpenApiResponse(description="Validation error / invalid credentials"),
        },
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            _record_attempt(request.data.get("username", ""), False, request)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        _record_attempt(user.username, True, request, user=user)
        return Response(
            {
                "token": token.key,
                "user": ShopUserSerializer(user).data,
                "requires_password_change": user.must_change_password,
            }
        )


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={
            200: MeResponseSerializer,
            401: OpenApiResponse(description="Authentication required"),
        }
    )
    def get(self, request):
        return Response({"user": ShopUserSerializer(request.user).data})


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=ChangePasswordSerializer,
        responses={
            200: AuthTokenResponseSerializer,
            400: OpenApiResponse(description="Validation error"),
            401: OpenApiResponse(description="Authentication required"),
        },
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        Token.objects.filter(user=user).delete()
        new_token = Token.objects.create(user=user)
        return Response(
            {
                "token": new_token.key,
                "user": ShopUserSerializer(user).data,
                "requires_password_change": user.must_change_password,
            }
        )
