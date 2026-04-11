import pyotp
from django.utils import timezone
from django.contrib.auth import authenticate
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from .models import LoginAttempt, ShopUser
from .emailing import send_branded_email


class ShopUserSerializer(serializers.ModelSerializer):
    two_factor_methods = serializers.SerializerMethodField()

    class Meta:
        model = ShopUser
        fields = [
            "id",
            "username",
            "name",
            "shop_code",
            "human_shop_id",
            "role",
            "status",
            "contact_phone",
            "contact_email",
            "wallet_balance",
            "commission_rate",
            "shop_cut_percentage",
            "lulu_cut_percentage",
            "max_stake",
            "feature_flags",
            "bank_name",
            "bank_account_name",
            "bank_account_number",
            "profile_completed",
            "two_factor_enabled",
            "two_factor_method",
            "two_factor_totp_enabled",
            "two_factor_email_enabled",
            "two_factor_methods",
            "must_change_password",
            "created_at",
        ]
        extra_kwargs = {
            "contact_email": {"required": True},
            "contact_phone": {"required": True},
        }

    def get_two_factor_methods(self, obj) -> list[str]:
        return obj.get_enabled_2fa_methods()


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    otp = serializers.CharField(write_only=True, required=False, allow_blank=True)
    resend_otp = serializers.BooleanField(required=False, default=False)

    @staticmethod
    def _mask_email(email: str) -> str:
        safe = (email or "").strip()
        if "@" not in safe:
            return safe

        local, domain = safe.split("@", 1)
        if not local:
            return f"****@{domain}"
        if len(local) == 1:
            return f"{local}****@{domain}"
        return f"{local[0]}****{local[-1]}@{domain}"

    @staticmethod
    def _send_login_email_code(user) -> bool:
        code = user.generate_email_2fa_code()
        user.save(update_fields=["two_factor_email_code", "two_factor_email_code_expires_at"])
        return send_branded_email(
            to_email=user.contact_email,
            subject="Your Lulu Bingo login verification code",
            heading="Login verification code",
            message=(
                f"Your login verification code is {code}. "
                "It expires in 10 minutes."
            ),
            banner_text="Login Verification",
        )

    @staticmethod
    def _get_client_ip(request) -> str | None:
        if request is None:
            return None
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")

    @staticmethod
    def _is_known_ip_for_user(user, ip_address: str | None) -> bool:
        if not ip_address:
            return False
        return LoginAttempt.objects.filter(
            user=user,
            success=True,
            ip_address=ip_address,
        ).exists()

    def validate(self, attrs):
        username = attrs.get("username")
        password = attrs.get("password")
        request = self.context.get("request")
        user = authenticate(request=request, username=username, password=password)
        if not user:
            try:
                shop = ShopUser.objects.get(username=username)
            except ShopUser.DoesNotExist:
                raise serializers.ValidationError("Invalid credentials. Please check your username and password.")

            if shop.status != ShopUser.Status.ACTIVE:
                raise serializers.ValidationError(
                    "Your shop is currently inactive. Please contact support for assistance."
                )

            raise serializers.ValidationError("Invalid credentials. Please check your username and password.")

        if user.role == ShopUser.Role.DEVELOPER:
            raise serializers.ValidationError(
                "This account type cannot access the admin API login.",
            )

        # Enforce OTP when 2FA is enabled
        request = self.context.get("request")
        otp = (attrs.get("otp") or "").strip()
        resend_otp = attrs.get("resend_otp", False)

        if user.role == ShopUser.Role.MANAGER:
            client_ip = self._get_client_ip(request)
            known_ip = self._is_known_ip_for_user(user, client_ip)

            if not known_ip:
                if not user.contact_email:
                    raise serializers.ValidationError(
                        {
                            "otp": "New-device verification is required, but no contact email is configured.",
                            "two_factor_method": "email_code",
                            "two_factor_methods": ["email_code"],
                        }
                    )

                if resend_otp or not otp:
                    if not self._send_login_email_code(user):
                        raise serializers.ValidationError(
                            {
                                "otp": "Could not send OTP email. Verify SMTP/email settings and try again.",
                                "two_factor_method": "email_code",
                                "two_factor_methods": ["email_code"],
                            }
                        )

                    raise serializers.ValidationError(
                        {
                            "otp": "OTP is required for login.",
                            "detail": "New device detected. A verification code has been sent to your email.",
                            "two_factor_method": "email_code",
                            "two_factor_methods": ["email_code"],
                            "email_hint": self._mask_email(user.contact_email),
                        }
                    )

                if not user.verify_email_2fa_code(otp):
                    raise serializers.ValidationError(
                        {
                            "otp": "Invalid or expired OTP",
                            "detail": "New device detected. Enter the verification code sent to your email.",
                            "two_factor_method": "email_code",
                            "two_factor_methods": ["email_code"],
                            "email_hint": self._mask_email(user.contact_email),
                        }
                    )

                user.clear_email_2fa_code()
                user.save(
                    update_fields=[
                        "two_factor_email_code",
                        "two_factor_email_code_expires_at",
                    ]
                )

            elif resend_otp:
                raise serializers.ValidationError(
                    {
                        "detail": "Current device is already recognized. New-device OTP is not required.",
                        "two_factor_method": "email_code",
                        "two_factor_methods": ["email_code"],
                    }
                )

            attrs["user"] = user
            return attrs

        if getattr(user, "two_factor_enabled", False):
            enabled_methods = user.get_enabled_2fa_methods()
            if not enabled_methods:
                fallback_method = getattr(user, "two_factor_method", "totp") or "totp"
                enabled_methods = [fallback_method]
            preferred_method = (
                user.two_factor_method
                if user.two_factor_method in enabled_methods
                else enabled_methods[0]
            )
            can_send_email_code = "email_code" in enabled_methods and bool(user.contact_email)

            if resend_otp:
                if not can_send_email_code:
                    raise serializers.ValidationError(
                        {
                            "otp": "Email OTP is not available for this account.",
                            "two_factor_method": preferred_method,
                            "two_factor_methods": enabled_methods,
                        }
                    )

                if not self._send_login_email_code(user):
                    raise serializers.ValidationError(
                        {
                            "otp": "Could not send OTP email. Verify SMTP/email settings and try again.",
                            "two_factor_method": "email_code",
                            "two_factor_methods": enabled_methods,
                        }
                    )

                raise serializers.ValidationError(
                    {
                        "otp": "OTP is required for login.",
                        "detail": "A new verification code has been sent to your email.",
                        "two_factor_method": "email_code",
                        "two_factor_methods": enabled_methods,
                        "email_hint": self._mask_email(user.contact_email),
                    }
                )

            if not otp:
                error_payload = {
                    "otp": "OTP is required for login.",
                    "two_factor_method": preferred_method,
                    "two_factor_methods": enabled_methods,
                }

                if can_send_email_code:
                    sent = self._send_login_email_code(user)
                    if sent:
                        error_payload["detail"] = (
                            "Verification code sent to your email."
                        )
                        error_payload["email_hint"] = self._mask_email(
                            user.contact_email
                        )
                    else:
                        error_payload["detail"] = (
                            "Could not send OTP email. Verify SMTP/email settings and try again."
                        )

                raise serializers.ValidationError(error_payload)

            otp_valid = False

            if "totp" in enabled_methods:
                if not user.totp_secret:
                    raise serializers.ValidationError("Two-factor is enabled but no secret is configured. Contact support.")
                totp = pyotp.TOTP(user.totp_secret)
                otp_valid = totp.verify(otp, valid_window=1)

            if not otp_valid and "email_code" in enabled_methods:
                otp_valid = user.verify_email_2fa_code(otp)
                if otp_valid:
                    user.clear_email_2fa_code()
                    user.save(update_fields=["two_factor_email_code", "two_factor_email_code_expires_at"])

            if not otp_valid:
                raise serializers.ValidationError(
                    {
                        "otp": "Invalid or expired OTP",
                        "two_factor_method": preferred_method,
                        "two_factor_methods": enabled_methods,
                        **(
                            {"email_hint": self._mask_email(user.contact_email)}
                            if can_send_email_code
                            else {}
                        ),
                    }
                )

        attrs["user"] = user
        return attrs


class LoginAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginAttempt
        fields = ["id", "username", "ip_address", "success", "timestamp", "user_agent"]


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    method = serializers.ChoiceField(choices=["totp", "email_code"], required=False)
    otp = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        if value.strip() == "":
            raise serializers.ValidationError("New password cannot be blank.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        user = self.context["request"].user

        current_password = attrs.get("current_password", "")
        new_password = attrs.get("new_password", "")
        if current_password and new_password and current_password == new_password:
            raise serializers.ValidationError({"new_password": "New password must be different from current password."})

        if not getattr(user, "two_factor_enabled", False):
            return attrs

        enabled_methods = user.get_enabled_2fa_methods()
        if not enabled_methods:
            fallback_method = getattr(user, "two_factor_method", "totp") or "totp"
            enabled_methods = [fallback_method]

        selected_method = attrs.get("method")
        if not selected_method:
            preferred_method = getattr(user, "two_factor_method", None)
            selected_method = preferred_method if preferred_method in enabled_methods else enabled_methods[0]

        if selected_method not in enabled_methods:
            raise serializers.ValidationError(
                {
                    "method": "Selected 2FA method is not enabled.",
                    "two_factor_methods": enabled_methods,
                }
            )

        otp = (attrs.get("otp") or "").strip()
        if not otp:
            raise serializers.ValidationError(
                {
                    "otp": "OTP code is required to change password.",
                    "two_factor_method": selected_method,
                    "two_factor_methods": enabled_methods,
                }
            )

        otp_valid = False

        if selected_method == "totp":
            if not user.totp_secret:
                raise serializers.ValidationError({"otp": "No TOTP secret is configured. Contact support."})
            totp = pyotp.TOTP(user.totp_secret)
            otp_valid = totp.verify(otp, valid_window=1)
        elif selected_method == "email_code":
            if not user.contact_email:
                raise serializers.ValidationError({"otp": "No contact email configured for email-code verification."})
            otp_valid = user.verify_email_2fa_code(otp)
            if otp_valid:
                user.clear_email_2fa_code()
                user.save(update_fields=["two_factor_email_code", "two_factor_email_code_expires_at"])

        if not otp_valid:
            raise serializers.ValidationError(
                {
                    "otp": "Invalid or expired OTP.",
                    "two_factor_method": selected_method,
                    "two_factor_methods": enabled_methods,
                }
            )

        attrs["method"] = selected_method
        return attrs


class AuthTokenResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    requires_password_change = serializers.BooleanField()
    missing_profile_fields = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )
    user = ShopUserSerializer(read_only=True)


class MeResponseSerializer(serializers.Serializer):
    user = ShopUserSerializer(read_only=True)


class ShopProfileSerializer(serializers.ModelSerializer):
    two_factor_methods = serializers.SerializerMethodField()

    class Meta:
        model = ShopUser
        fields = [
            "username",
            "name",
            "shop_code",
            "human_shop_id",
            "role",
            "contact_phone",
            "contact_email",
            "bank_name",
            "bank_account_name",
            "bank_account_number",
            "profile_completed",
            "status",
            "wallet_balance",
            "commission_rate",
            "shop_cut_percentage",
            "lulu_cut_percentage",
            "max_stake",
            "feature_flags",
            "two_factor_enabled",
            "two_factor_method",
            "two_factor_totp_enabled",
            "two_factor_email_enabled",
            "two_factor_methods",
            "created_at",
        ]
        read_only_fields = [
            "username",
            "shop_code",
            "human_shop_id",
            "status",
            "wallet_balance",
            "commission_rate",
            "shop_cut_percentage",
            "lulu_cut_percentage",
            "max_stake",
            "two_factor_enabled",
            "two_factor_method",
            "two_factor_totp_enabled",
            "two_factor_email_enabled",
            "two_factor_methods",
            "created_at",
        ]

    def get_two_factor_methods(self, obj) -> list[str]:
        return obj.get_enabled_2fa_methods()

    def validate(self, attrs):
        if attrs and set(attrs.keys()) <= {"feature_flags"}:
            return attrs

        instance = self.instance or ShopUser()
        errors: dict[str, str] = {}
        required_fields = [
            "name",
            "contact_email",
            "contact_phone",
            "bank_name",
            "bank_account_name",
            "bank_account_number",
        ]
        for field in required_fields:
            value = attrs.get(field, getattr(instance, field, ""))
            if isinstance(value, str):
                value = value.strip()
            if not value:
                errors[field] = "This field is required to finalize your profile."

        contact_email = attrs.get("contact_email", getattr(instance, "contact_email", ""))
        contact_phone = attrs.get("contact_phone", getattr(instance, "contact_phone", ""))

        if contact_email:
            duplicate_email = (
                ShopUser.objects.filter(contact_email__iexact=contact_email)
                .exclude(pk=getattr(instance, "pk", None))
                .exists()
            )
            if duplicate_email:
                errors["contact_email"] = "This email is already used by another shop."

        if contact_phone:
            duplicate_phone = (
                ShopUser.objects.filter(contact_phone=contact_phone)
                .exclude(pk=getattr(instance, "pk", None))
                .exists()
            )
            if duplicate_phone:
                errors["contact_phone"] = "This phone number is already used by another shop."

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def update(self, instance, validated_data):
        profile_completion_fields = {
            "name",
            "contact_phone",
            "contact_email",
            "bank_name",
            "bank_account_name",
            "bank_account_number",
        }

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if profile_completion_fields.intersection(validated_data.keys()):
            instance.profile_completed = all(
                bool(str(getattr(instance, field_name, "")).strip())
                for field_name in profile_completion_fields
            )

        instance.save()
        return instance


class PasswordResetRequestSerializer(serializers.Serializer):
    username = serializers.CharField(required=False, allow_blank=True)
    contact_email = serializers.EmailField(required=False, allow_blank=True)

    def validate(self, attrs):
        username = attrs.get("username")
        email = attrs.get("contact_email")
        user = None

        if username:
            user = ShopUser.objects.filter(username=username).first()
        if not user and email:
            user = ShopUser.objects.filter(contact_email=email).first()

        attrs["user"] = user
        return attrs


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        uid = attrs.get("uid")
        token = attrs.get("token")
        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = ShopUser.objects.get(pk=user_id)
        except Exception:
            raise serializers.ValidationError("Invalid reset token")

        if not default_token_generator.check_token(user, token):
            raise serializers.ValidationError("Invalid or expired reset token")

        attrs["user"] = user
        return attrs


class TwoFactorSetupSerializer(serializers.Serializer):
    secret = serializers.CharField(read_only=True)
    provisioning_uri = serializers.CharField(read_only=True)


class TwoFactorEnableSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=["totp", "email_code"], required=True)
    otp = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = self.context["request"].user
        method = attrs.get("method")
        otp = attrs.get("otp")

        if method == "totp":
            if not user.totp_secret:
                raise serializers.ValidationError("No TOTP secret is set. Generate one first.")
            totp = pyotp.TOTP(user.totp_secret)
            if not totp.verify(otp, valid_window=1):
                raise serializers.ValidationError({"otp": "Invalid or expired OTP"})
        else:
            if not user.contact_email:
                raise serializers.ValidationError({"otp": "No contact email configured for email 2FA"})
            if not user.verify_email_2fa_code(otp):
                raise serializers.ValidationError({"otp": "Invalid or expired OTP"})

        attrs["user"] = user
        return attrs


class TwoFactorDisableSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=["totp", "email_code"], required=False)
    otp = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = self.context["request"].user
        enabled_methods = user.get_enabled_2fa_methods()
        method = attrs.get("method")

        if not enabled_methods:
            raise serializers.ValidationError({"detail": "Two-factor is not enabled."})

        if not method:
            if len(enabled_methods) == 1:
                method = enabled_methods[0]
            else:
                raise serializers.ValidationError({"method": "Specify which two-factor method to disable."})

        if method not in enabled_methods:
            raise serializers.ValidationError({"method": "Selected method is not currently enabled."})

        otp = attrs.get("otp")

        if method == "totp":
            if not user.totp_secret:
                raise serializers.ValidationError("No TOTP secret is set.")
            totp = pyotp.TOTP(user.totp_secret)
            if not totp.verify(otp, valid_window=1):
                raise serializers.ValidationError({"otp": "Invalid or expired OTP"})
        else:
            if not user.contact_email:
                raise serializers.ValidationError({"otp": "No contact email configured for email 2FA"})
            if not user.verify_email_2fa_code(otp):
                raise serializers.ValidationError({"otp": "Invalid or expired OTP"})

        attrs["user"] = user
        attrs["method"] = method
        return attrs


class TwoFactorEmailCodeSerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=["enable", "disable", "change_password"])

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.contact_email:
            raise serializers.ValidationError({"detail": "Contact email is required for email-code 2FA."})
        return attrs
