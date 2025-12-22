from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import LoginAttempt, ShopUser


@admin.register(ShopUser)
class ShopUserAdmin(UserAdmin):
    model = ShopUser
    list_display = ("username", "name", "status", "wallet_balance", "must_change_password", "created_at")
    list_filter = ("status", "must_change_password", "created_at")
    search_fields = ("username", "name", "contact_phone", "contact_email")
    ordering = ("username",)
    readonly_fields = ("created_at",)
    fieldsets = (
        (None, {"fields": ("username", "name", "password", "status", "must_change_password")}),
        ("Contact", {"fields": ("contact_phone", "contact_email")}),
        (
            "Operational",
            {"fields": ("wallet_balance", "commission_rate", "max_stake", "feature_flags")},
        ),
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
