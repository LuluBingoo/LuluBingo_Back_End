from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import LoginAttempt, ShopUser


@admin.register(ShopUser)
class ShopUserAdmin(UserAdmin):
    model = ShopUser
    list_display = ("username", "is_active", "is_staff", "created_at")
    search_fields = ("username",)
    ordering = ("username",)
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "created_at")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "password1", "password2", "is_staff", "is_superuser"),
        }),
    )


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("username", "success", "ip_address", "timestamp")
    search_fields = ("username", "ip_address")
    list_filter = ("success", "timestamp")
