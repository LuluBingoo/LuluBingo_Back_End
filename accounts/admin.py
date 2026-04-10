from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import LoginAttempt, ShopUser


# Site branding
from django.contrib import admin as dj_admin

dj_admin.site.site_header = "LuluBingo Admin"
dj_admin.site.site_title = "LuluBingo"
dj_admin.site.index_title = "Dashboard"
dj_admin.site.site_url = "/"


@admin.register(ShopUser)
class ShopUserAdmin(UserAdmin):
    model = ShopUser
    list_display = (
        "username",
        "role",
        "shop_code",
        "name",
        "contact_email",
        "status",
        "profile_completed",
        "wallet_balance",
        "shop_cut_percentage",
        "lulu_cut_percentage",
        "must_change_password",
        "two_factor_enabled",
        "created_at",
    )
    list_filter = (
        "role",
        "status",
        "must_change_password",
        "profile_completed",
        "two_factor_enabled",
        "created_at",
    )
    search_fields = ("username", "name", "contact_phone", "contact_email")
    ordering = ("username",)
    readonly_fields = ("created_at", "shop_code", "totp_secret")
    actions = [
        "activate_users",
        "suspend_users",
        "mark_profiles_complete",
        "reset_two_factor",
        "promote_to_manager",
    ]
    fieldsets = (
        (None, {
            "fields": (
                "username",
                "shop_code",
                "name",
                "password",
                "role",
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
            {
                "fields": (
                    "wallet_balance",
                    "commission_rate",
                    "shop_cut_percentage",
                    "lulu_cut_percentage",
                    "max_stake",
                    "feature_flags",
                )
            },
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
                "contact_phone",
                "contact_email",
                "password1",
                "password2",
                "role",
                "status",
                "must_change_password",
                "two_factor_method",
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

    def promote_to_manager(self, request, queryset):
        updated = 0
        for user in queryset:
            if user.role == ShopUser.Role.MANAGER and user.is_staff:
                continue
            user.role = ShopUser.Role.MANAGER
            user.is_staff = True
            if user.status == ShopUser.Status.PENDING:
                user.status = ShopUser.Status.ACTIVE
            user.save(update_fields=["role", "is_staff", "status"])
            updated += 1
        self.message_user(request, f"Promoted {updated} user(s) to manager.")

    promote_to_manager.short_description = "Promote selected users to manager"


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("username", "success", "ip_address", "timestamp")
    search_fields = ("username", "ip_address")
    list_filter = ("success", "timestamp")
