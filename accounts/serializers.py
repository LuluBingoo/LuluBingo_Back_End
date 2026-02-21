import pyotp
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.contrib.auth import authenticate
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from .models import LoginAttempt, ShopUser


class ShopUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopUser
        fields = [
            "id",
            "username",
            "name",
            "shop_code",
            "human_shop_id",
            "status",
            "contact_phone",
            "contact_email",
            "wallet_balance",
            "commission_rate",
            "max_stake",
            "feature_flags",
            "bank_name",
            "bank_account_name",
            "bank_account_number",
            "profile_completed",
            "two_factor_enabled",
            "two_factor_method",
            "must_change_password",
            "created_at",
        ]
        extra_kwargs = {
            "contact_email": {"required": True},
            "contact_phone": {"required": True},
        }


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    otp = serializers.CharField(write_only=True, required=False, allow_blank=True)

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
        # Enforce OTP when 2FA is enabled
        if getattr(user, "two_factor_enabled", False):
            method = getattr(user, "two_factor_method", "totp") or "totp"
            otp = attrs.get("otp")

            if method == "totp":
                if not otp:
                    raise serializers.ValidationError(
                        {
                            "otp": "OTP code required",
                            "two_factor_method": method,
                        }
                    )
                if not user.totp_secret:
                    raise serializers.ValidationError("Two-factor is enabled but no secret is configured. Contact support.")
                totp = pyotp.TOTP(user.totp_secret)
                if not totp.verify(otp, valid_window=1):
                    raise serializers.ValidationError(
                        {
                            "otp": "Invalid or expired OTP",
                            "two_factor_method": method,
                        }
                    )
            elif method == "email_code":
                if not user.contact_email:
                    raise serializers.ValidationError(
                        {
                            "otp": "No contact email configured for email 2FA",
                            "two_factor_method": method,
                        }
                    )

                if not otp:
                    code = user.generate_email_2fa_code()
                    user.save(update_fields=["two_factor_email_code", "two_factor_email_code_expires_at"])
                    send_mail(
                        "Your Lulu Bingo login code",
                        f"Your verification code is: {code}. It expires in 10 minutes.",
                        getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@lulu-bingo.local"),
                        [user.contact_email],
                        fail_silently=getattr(settings, "EMAIL_FAIL_SILENTLY", False),
                    )
                    raise serializers.ValidationError(
                        {
                            "otp": "OTP code required. A code was sent to your email.",
                            "two_factor_method": method,
                        }
                    )

                if not user.verify_email_2fa_code(otp):
                    raise serializers.ValidationError(
                        {
                            "otp": "Invalid or expired OTP",
                            "two_factor_method": method,
                        }
                    )

                user.clear_email_2fa_code()
                user.save(update_fields=["two_factor_email_code", "two_factor_email_code_expires_at"])
            else:
                raise serializers.ValidationError(
                    {
                        "otp": "Unsupported two-factor method",
                        "two_factor_method": method,
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


class ShopProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopUser
        fields = [
            "username",
            "name",
            "shop_code",
            "human_shop_id",
            "contact_phone",
            "contact_email",
            "bank_name",
            "bank_account_name",
            "bank_account_number",
            "profile_completed",
            "status",
            "wallet_balance",
            "commission_rate",
            "max_stake",
            "feature_flags",
            "two_factor_enabled",
            "two_factor_method",
            "created_at",
        ]
        read_only_fields = [
            "username",
            "shop_code",
            "human_shop_id",
            "status",
            "wallet_balance",
            "commission_rate",
            "max_stake",
            "two_factor_enabled",
            "two_factor_method",
            "created_at",
        ]

    def validate(self, attrs):
        if attrs and set(attrs.keys()) <= {"feature_flags"}:
            return attrs

        instance = self.instance or ShopUser()
        errors: dict[str, str] = {}
        required_fields = ["contact_email", "contact_phone"]
        for field in required_fields:
            value = attrs.get(field, getattr(instance, field, ""))
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
            instance.profile_completed = True

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
        method = attrs.get("method") or user.two_factor_method
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
    purpose = serializers.ChoiceField(choices=["enable", "disable"])

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.contact_email:
            raise serializers.ValidationError({"detail": "Contact email is required for email-code 2FA."})
        return attrs
