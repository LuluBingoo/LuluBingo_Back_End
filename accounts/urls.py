from django.urls import path

from .views import ChangePasswordView, LoginView, MeView

urlpatterns = [
    path("auth/login", LoginView.as_view(), name="login"),
    path("auth/me", MeView.as_view(), name="me"),
    path("auth/password/change", ChangePasswordView.as_view(), name="password-change"),
]
