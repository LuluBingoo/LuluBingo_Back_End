from django.urls import path

from .admin_views import (
    AdminGameListView,
    AdminManagerDetailView,
    AdminManagerListCreateView,
    AdminShopBalanceTopUpView,
    AdminShopDetailView,
    AdminShopListCreateView,
    AdminTransactionListView,
)
from .views import (
    ChangePasswordView,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ShopProfileView,
    TwoFactorDisableView,
    TwoFactorEmailCodeView,
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
    path("auth/2fa/email-code", TwoFactorEmailCodeView.as_view(), name="2fa-email-code"),
    path("admin/managers", AdminManagerListCreateView.as_view(), name="admin-managers"),
    path("admin/managers/<int:user_id>", AdminManagerDetailView.as_view(), name="admin-manager-detail"),
    path("admin/shops", AdminShopListCreateView.as_view(), name="admin-shops"),
    path("admin/shops/<int:user_id>", AdminShopDetailView.as_view(), name="admin-shop-detail"),
    path("admin/shops/<int:user_id>/fill-balance", AdminShopBalanceTopUpView.as_view(), name="admin-shop-fill-balance"),
    path("admin/games", AdminGameListView.as_view(), name="admin-games"),
    path("admin/transactions", AdminTransactionListView.as_view(), name="admin-transactions"),
    path("shop/profile", ShopProfileView.as_view(), name="shop-profile"),
]
