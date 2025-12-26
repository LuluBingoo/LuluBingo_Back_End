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
        "contact_email",
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
    actions = ["activate_users", "suspend_users", "mark_profiles_complete", "reset_two_factor"]
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

    def _update_users(self, request, queryset, **updates):
        updated = 0
        for user in queryset:
            for field, value in updates.items():
                setattr(user, field, value)
            user.save(update_fields=list(updates.keys()))
            updated += 1
        return updated

    def activate_users(self, request, queryset):
        updated = self._update_users(
            request,
            queryset,
            status=ShopUser.Status.ACTIVE,
            must_change_password=False,
        )
        self.message_user(request, f"Activated {updated} shop(s).")

    activate_users.short_description = "Mark selected shops active"

    def suspend_users(self, request, queryset):
        updated = self._update_users(request, queryset, status=ShopUser.Status.SUSPENDED)
        self.message_user(request, f"Suspended {updated} shop(s).")

    suspend_users.short_description = "Suspend selected shops"

    def mark_profiles_complete(self, request, queryset):
        updated = self._update_users(request, queryset, profile_completed=True)
        self.message_user(request, f"Marked {updated} profile(s) complete.")

    mark_profiles_complete.short_description = "Mark profile completed"

    def reset_two_factor(self, request, queryset):
        updated = 0
        for user in queryset:
            user.two_factor_enabled = False
            user.totp_secret = ""
            user.save(update_fields=["two_factor_enabled", "totp_secret"])
            updated += 1
        self.message_user(request, f"Reset 2FA for {updated} shop(s).")

    reset_two_factor.short_description = "Disable 2FA and clear secret"


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("username", "success", "ip_address", "timestamp")
    search_fields = ("username", "ip_address")
    list_filter = ("success", "timestamp")
