from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import LoginAttempt, ShopUser


@admin.register(ShopUser)
class ShopUserAdmin(UserAdmin):
    model = ShopUser
    list_display = (
        "username",
        "shop_code",
        "name",
        "status",
        "profile_completed",
        "wallet_balance",
        "must_change_password",
        "two_factor_enabled",
        "created_at",
    )
    list_filter = ("status", "must_change_password", "profile_completed", "two_factor_enabled", "created_at")
    search_fields = ("username", "name", "contact_phone", "contact_email")
    ordering = ("username",)
    readonly_fields = ("created_at", "shop_code", "totp_secret")
    fieldsets = (
        (None, {
            "fields": (
                "username",
                "shop_code",
                "name",
                "password",
                "status",
                "profile_completed",
                "must_change_password",
                "two_factor_enabled",
                "two_factor_method",
                "totp_secret",
            )
        }),
        ("Contact", {"fields": ("contact_phone", "contact_email")}),
        (
            "Operational",
            {"fields": ("wallet_balance", "commission_rate", "max_stake", "feature_flags")},
        ),
        ("Banking", {"fields": ("bank_name", "bank_account_name", "bank_account_number")}),
        (
            "Permissions",
            {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login", "created_at")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "username",
                "name",
                "password1",
                "password2",
                "status",
                "must_change_password",
                "is_staff",
                "is_superuser",
            ),
        }),
    )


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("username", "success", "ip_address", "timestamp")
    search_fields = ("username", "ip_address")
    list_filter = ("success", "timestamp")
