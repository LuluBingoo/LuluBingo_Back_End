import os
import re
import ipaddress
import json
from functools import lru_cache
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
import pyotp
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import JsonResponse

from .models import LoginAttempt
from .emailing import send_branded_email
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


@lru_cache(maxsize=512)
def _lookup_address_from_ip(ip_address: str) -> str:
    if not ip_address:
        return "Address unavailable"

    try:
        parsed_ip = ipaddress.ip_address(ip_address)
    except ValueError:
        return "Address unavailable"

    if parsed_ip.is_private or parsed_ip.is_loopback or parsed_ip.is_link_local:
        return "Local/Private network"

    lookup_url_template = getattr(settings, "IP_GEO_LOOKUP_URL", "https://ipwho.is/{ip}")
    timeout = float(getattr(settings, "IP_GEO_LOOKUP_TIMEOUT", 1.5))

    try:
        lookup_url = lookup_url_template.format(ip=ip_address)
        request = Request(lookup_url, headers={"User-Agent": "LuluBingo/1.0"})
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return "Address unavailable"

    if isinstance(payload, dict) and payload.get("success") is False:
        return "Address unavailable"

    city = str(payload.get("city") or "").strip()
    region = str(payload.get("region") or payload.get("region_name") or "").strip()
    country = str(payload.get("country") or payload.get("country_name") or "").strip()

    parts = [part for part in (city, region, country) if part]
    if parts:
        return ", ".join(parts)
    return "Address unavailable"


def _get_client_address(request) -> str:
    meta = request.META
    city = (
        meta.get("HTTP_CF_IPCITY")
        or meta.get("HTTP_X_APPENGINE_CITY")
        or meta.get("HTTP_X_CITY")
        or meta.get("HTTP_GEOIP_CITY")
        or ""
    ).strip()
    region = (
        meta.get("HTTP_CF_REGION")
        or meta.get("HTTP_X_APPENGINE_REGION")
        or meta.get("HTTP_X_REGION")
        or meta.get("HTTP_GEOIP_REGION")
        or ""
    ).strip()
    country = (
        meta.get("HTTP_CF_IPCOUNTRY")
        or meta.get("HTTP_X_APPENGINE_COUNTRY")
        or meta.get("HTTP_X_COUNTRY")
        or meta.get("HTTP_X_COUNTRY_CODE")
        or meta.get("HTTP_GEOIP_COUNTRY_NAME")
        or ""
    ).strip()

    parts = [part for part in (city, region, country) if part]
    if parts:
        return ", ".join(parts)

    return _lookup_address_from_ip(_get_client_ip(request) or "")


def _get_browser_name(request) -> str:
    user_agent = (request.META.get("HTTP_USER_AGENT") or "").strip().lower()
    if not user_agent:
        return "Unknown browser"

    browser_checks = [
        (r"edg/", "Microsoft Edge"),
        (r"opr/|opera", "Opera"),
        (r"firefox|fxios", "Firefox"),
        (r"samsungbrowser", "Samsung Internet"),
        (r"chrome|crios", "Google Chrome"),
        (r"safari", "Safari"),
        (r"trident|msie", "Internet Explorer"),
        (r"postmanruntime", "Postman Runtime"),
        (r"curl", "curl"),
        (r"httpie", "HTTPie"),
    ]
    for pattern, browser_name in browser_checks:
        if re.search(pattern, user_agent):
            if browser_name == "Safari" and re.search(r"chrome|crios|opr/|edg/", user_agent):
                continue
            return browser_name
    return "Unknown browser"


def _get_device_os(request) -> str:
    user_agent = (request.META.get("HTTP_USER_AGENT") or "").strip().lower()
    if not user_agent:
        return "Unknown device"

    if "iphone" in user_agent:
        return "iPhone (iOS)"
    if "ipad" in user_agent:
        return "iPad (iPadOS)"
    if "android" in user_agent:
        return "Android device"
    if "windows" in user_agent:
        return "Windows"
    if "mac os x" in user_agent or "macintosh" in user_agent:
        return "macOS"
    if "linux" in user_agent:
        return "Linux"
    return "Unknown device"


def _record_attempt(username: str, success: bool, request, user=None):
    LoginAttempt.objects.create(
        username=username,
        success=success,
        ip_address=_get_client_ip(request),
        user=user if success else None,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:512],
        timestamp=timezone.now(),
    )


def _send_security_email(user, subject: str, message: str) -> bool:
    # Skip when email is missing to avoid noisy failures.
    if not user or not user.contact_email:
        return False

    return send_branded_email(
        to_email=user.contact_email,
        subject=subject,
        heading=subject,
        message=message,
    )


def _get_missing_profile_fields(user) -> list[str]:
    if not user:
        return []

    required_fields = [
        "name",
        "contact_email",
        "contact_phone",
        "bank_name",
        "bank_account_name",
        "bank_account_number",
    ]
    missing_fields: list[str] = []

    for field_name in required_fields:
        value = getattr(user, field_name, None)
        if isinstance(value, str):
            value = value.strip()
        if not value:
            missing_fields.append(field_name)

    profile_completed = len(missing_fields) == 0
    if user.profile_completed != profile_completed:
        user.profile_completed = profile_completed
        user.save(update_fields=["profile_completed"])

    return missing_fields


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
        missing_profile_fields = _get_missing_profile_fields(user)
        login_time = timezone.now()
        ip_address = _get_client_ip(request) or "unknown"
        client_address = _get_client_address(request)
        browser_name = _get_browser_name(request)
        device_os = _get_device_os(request)
        _send_security_email(
            user,
            "Login notification",
            (
                "A login to your shop account was detected.\n"
                f"Time: {login_time:%Y-%m-%d %H:%M:%S}\n"
                f"Address: {client_address}\n"
                f"IP: {ip_address}\n"
                f"Browser: {browser_name}\n\n"
                f"Device/OS: {device_os}\n\n"
                "If this wasn't you, set up 2FA and change your password immediately."
            ),
        )
        return Response(
            {
                "token": token.key,
                "user": ShopUserSerializer(user).data,
                "requires_password_change": user.must_change_password,
                "missing_profile_fields": missing_profile_fields,
            }
        )


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=None,
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
                "missing_profile_fields": _get_missing_profile_fields(user),
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
        updated_fields = set(serializer.validated_data.keys())
        user = serializer.save()
        if updated_fields - {"feature_flags"}:
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
            send_branded_email(
                to_email=user.contact_email,
                subject="Password reset requested",
                heading="Reset your password",
                message=(
                    "We received a request to reset your shop password. "
                    "Click the button below to complete the reset. If this wasn't you, ignore this email."
                ),
                cta_text="Reset Password",
                cta_url=reset_link,
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

        if method == "totp":
            user.two_factor_totp_enabled = True
            user.two_factor_method = "totp"
        else:
            user.two_factor_email_enabled = True
            if user.two_factor_method not in user.get_enabled_2fa_methods():
                user.two_factor_method = "email_code"

        user.sync_two_factor_status()
        user.clear_email_2fa_code()
        user.save(
            update_fields=[
                "two_factor_enabled",
                "two_factor_method",
                "two_factor_totp_enabled",
                "two_factor_email_enabled",
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
        method = serializer.validated_data["method"]

        if method == "totp":
            user.two_factor_totp_enabled = False
        elif method == "email_code":
            user.two_factor_email_enabled = False

        user.sync_two_factor_status()
        user.clear_email_2fa_code()
        user.save(
            update_fields=[
                "two_factor_enabled",
                "two_factor_method",
                "two_factor_totp_enabled",
                "two_factor_email_enabled",
                "two_factor_email_code",
                "two_factor_email_code_expires_at",
            ]
        )
        _send_security_email(
            user,
            "Two-factor disabled",
            f"Two-factor authentication ({method}) was disabled on your shop account. If this wasn't you, enable it again and contact support.",
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

        sent = _send_security_email(
            user,
            "Your Lulu Bingo verification code",
            f"Your verification code is: {code}. It expires in 10 minutes. Purpose: {purpose}.",
        )

        if not sent:
            return Response(
                {
                    "detail": "Could not send OTP email. Verify SMTP/email settings and try again.",
                    "purpose": purpose,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({"detail": "Verification code sent to your email.", "purpose": purpose})


class HealthCheckView(APIView):
    def get(self, request):
        return JsonResponse({"status": "Backend is working!"})
