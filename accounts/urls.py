from django.urls import path

from .views import (
    ChangePasswordView,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ShopProfileView,
    TwoFactorDisableView,
    TwoFactorEnableView,
    TwoFactorSetupView,
)

urlpatterns = [
    path("auth/login", LoginView.as_view(), name="login"),
    path("auth/logout", LogoutView.as_view(), name="logout"),
    path("auth/me", MeView.as_view(), name="me"),
    path("auth/password/change", ChangePasswordView.as_view(), name="password-change"),
    path("auth/password/forgot", PasswordResetRequestView.as_view(), name="password-forgot"),
    path("auth/password/reset", PasswordResetConfirmView.as_view(), name="password-reset"),
    path("auth/2fa/setup", TwoFactorSetupView.as_view(), name="2fa-setup"),
    path("auth/2fa/enable", TwoFactorEnableView.as_view(), name="2fa-enable"),
    path("auth/2fa/disable", TwoFactorDisableView.as_view(), name="2fa-disable"),
    path("shop/profile", ShopProfileView.as_view(), name="shop-profile"),
]
