import os

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
import pyotp
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
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ShopProfileSerializer,
    ShopUserSerializer,
    TwoFactorDisableSerializer,
    TwoFactorEmailCodeSerializer,
    TwoFactorEnableSerializer,
    TwoFactorSetupSerializer,
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


def _send_security_email(user, subject: str, message: str):
    # Skip when email is missing to avoid noisy failures.
    if not user or not user.contact_email:
        return

    send_mail(
        subject,
        message,
        getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@lulu-bingo.local"),
        [user.contact_email],
        fail_silently=getattr(settings, "EMAIL_FAIL_SILENTLY", False),
    )


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=LoginSerializer,
        responses={
            200: AuthTokenResponseSerializer,
            400: OpenApiResponse(description="Validation error / invalid credentials"),
        },
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            _record_attempt(request.data.get("username", ""), False, request)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        _record_attempt(user.username, True, request, user=user)
        _send_security_email(
            user,
            "Login notification",
            f"A login to your shop account occurred at {timezone.now():%Y-%m-%d %H:%M:%S} from IP {_get_client_ip(request) or 'unknown'}.",
        )
        return Response(
            {
                "token": token.key,
                "user": ShopUserSerializer(user).data,
                "requires_password_change": user.must_change_password,
            }
        )


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={200: OpenApiResponse(description="Token invalidated")},
        tags=["Authentication"],
    )
    def post(self, request):
        try:
            request.user.auth_token.delete()
        except (AttributeError, Token.DoesNotExist):
            pass
        return Response({"detail": "Successfully logged out."})


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={
            200: MeResponseSerializer,
            401: OpenApiResponse(description="Authentication required"),
        },
        tags=["Authentication"],
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
        tags=["Authentication"],
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
        _send_security_email(
            user,
            "Password changed",
            "Your shop account password was changed successfully. If this wasn't you, please reset your password immediately.",
        )
        return Response(
            {
                "token": new_token.key,
                "user": ShopUserSerializer(user).data,
                "requires_password_change": user.must_change_password,
            }
        )


class ShopProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={
            200: ShopProfileSerializer,
            401: OpenApiResponse(description="Authentication required"),
        },
        tags=["Shop"],
    )
    def get(self, request):
        return Response(ShopProfileSerializer(request.user).data)

    @extend_schema(
        request=ShopProfileSerializer,
        responses={
            200: ShopProfileSerializer,
            400: OpenApiResponse(description="Validation error"),
            401: OpenApiResponse(description="Authentication required"),
        },
        tags=["Shop"],
    )
    def put(self, request):
        serializer = ShopProfileSerializer(instance=request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        _send_security_email(
            user,
            "Profile updated",
            "Your shop profile was updated. If you did not make this change, please contact support immediately.",
        )
        return Response(serializer.data)


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=PasswordResetRequestSerializer,
        responses={200: OpenApiResponse(description="Reset email sent")},
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data.get("user")

        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)

            reset_link = request.build_absolute_uri(
                f"/api/auth/password/reset/confirm?uid={uid}&token={token}"
            )
            _send_security_email(
                user,
                "Password reset requested",
                "We received a request to reset your shop password. "
                f"Use this link to complete it: {reset_link}. If this wasn't you, you can ignore this email.",
            )

        return Response({"detail": "If the account exists, a reset email has been sent."})


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=PasswordResetConfirmSerializer,
        responses={
            200: AuthTokenResponseSerializer,
            400: OpenApiResponse(description="Invalid token or data"),
        },
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])

        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)

        _send_security_email(
            user,
            "Password reset successful",
            "Your shop password was reset. If you didn't perform this action, contact support immediately.",
        )

        return Response(
            {
                "token": token.key,
                "user": ShopUserSerializer(user).data,
                "requires_password_change": user.must_change_password,
            }
        )


class TwoFactorSetupView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={200: TwoFactorSetupSerializer},
        tags=["Authentication"],
    )
    def get(self, request):
        user = request.user
        user.ensure_totp_secret()
        user.save(update_fields=["totp_secret"])

        issuer = os.getenv("TWO_FACTOR_ISSUER", "LuluBingo")
        label = f"{issuer}:{user.username}"
        totp = pyotp.TOTP(user.totp_secret)
        uri = totp.provisioning_uri(name=label, issuer_name=issuer)
        data = {"secret": user.totp_secret, "provisioning_uri": uri}
        return Response(data)


class TwoFactorEnableView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=TwoFactorEnableSerializer,
        responses={200: ShopUserSerializer},
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = TwoFactorEnableSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        method = serializer.validated_data["method"]
        user.two_factor_enabled = True
        user.two_factor_method = method
        user.clear_email_2fa_code()
        user.save(
            update_fields=[
                "two_factor_enabled",
                "two_factor_method",
                "two_factor_email_code",
                "two_factor_email_code_expires_at",
            ]
        )
        _send_security_email(
            user,
            "Two-factor enabled",
            f"Two-factor authentication ({method}) was enabled on your shop account.",
        )
        return Response(ShopUserSerializer(user).data)


class TwoFactorDisableView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=TwoFactorDisableSerializer,
        responses={200: ShopUserSerializer},
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = TwoFactorDisableSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.two_factor_enabled = False
        user.clear_email_2fa_code()
        user.save(
            update_fields=[
                "two_factor_enabled",
                "two_factor_email_code",
                "two_factor_email_code_expires_at",
            ]
        )
        _send_security_email(
            user,
            "Two-factor disabled",
            "Two-factor authentication was disabled on your shop account. If this wasn't you, enable it again and contact support.",
        )
        return Response(ShopUserSerializer(user).data)


class TwoFactorEmailCodeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=TwoFactorEmailCodeSerializer,
        responses={200: OpenApiResponse(description="Email code sent")},
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = TwoFactorEmailCodeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        user = request.user
        purpose = serializer.validated_data["purpose"]
        code = user.generate_email_2fa_code()
        user.save(update_fields=["two_factor_email_code", "two_factor_email_code_expires_at"])

        _send_security_email(
            user,
            "Your Lulu Bingo verification code",
            f"Your verification code is: {code}. It expires in 10 minutes. Purpose: {purpose}.",
        )

        return Response({"detail": "Verification code sent to your email.", "purpose": purpose})
