from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import LoginAttempt
from .serializers import LoginSerializer, ShopUserSerializer


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

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            _record_attempt(request.data.get("username", ""), False, request)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        _record_attempt(user.username, True, request, user=user)
        return Response({"token": token.key, "user": ShopUserSerializer(user).data})


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({"user": ShopUserSerializer(request.user).data})
