import pyotp
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase

from .models import ShopUser, LoginAttempt


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AuthTests(APITestCase):
    def setUp(self):
        self.user = ShopUser.objects.create_user(
            username="shop1",
            password="pass1234",
            name="Shop One",
            contact_email="shop1@example.com",
        )
        self.user.status = ShopUser.Status.ACTIVE
        self.user.must_change_password = False
        self.user.save()

    def test_login_success_and_attempt_logged(self):
        url = reverse("login")
        resp = self.client.post(url, {"username": "shop1", "password": "pass1234"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("token", resp.data)
        self.assertIn("requires_password_change", resp.data)
        attempt = LoginAttempt.objects.first()
        self.assertIsNotNone(attempt)
        self.assertTrue(attempt.success)
        self.assertEqual(attempt.username, "shop1")

    def test_login_failure_and_attempt_logged(self):
        url = reverse("login")
        resp = self.client.post(url, {"username": "shop1", "password": "wrong"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        attempt = LoginAttempt.objects.first()
        self.assertIsNotNone(attempt)
        self.assertFalse(attempt.success)
        self.assertEqual(attempt.username, "shop1")

    def test_me_requires_auth(self):
        url = reverse("me")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_user_when_authenticated(self):
        url = reverse("login")
        resp = self.client.post(url, {"username": "shop1", "password": "pass1234"}, format="json")
        token = resp.data["token"]
        me_url = reverse("me")
        resp_me = self.client.get(me_url, HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(resp_me.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_me.data["user"]["username"], "shop1")

    def test_login_blocked_when_shop_not_active(self):
        pending = ShopUser.objects.create_user(
            username="pending",
            password="temp1234",
            name="Pending Shop",
            contact_email="pending@example.com",
        )
        pending.status = ShopUser.Status.PENDING
        pending.save()
        url = reverse("login")
        resp = self.client.post(url, {"username": "pending", "password": "temp1234"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_requires_current_password(self):
        url = reverse("login")
        login_resp = self.client.post(url, {"username": "shop1", "password": "pass1234"}, format="json")
        token = login_resp.data["token"]
        change_url = reverse("password-change")
        resp = self.client.post(
            change_url,
            {"current_password": "bad", "new_password": "newpass789"},
            format="json",
            HTTP_AUTHORIZATION=f"Token {token}",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_rotates_token_and_clears_flag(self):
        user = ShopUser.objects.create_user(
            username="shop2",
            password="temp1234",
            name="Shop Two",
            contact_email="shop2@example.com",
        )
        user.status = ShopUser.Status.ACTIVE
        user.must_change_password = True
        user.save()

        login_resp = self.client.post(
            reverse("login"), {"username": "shop2", "password": "temp1234"}, format="json"
        )
        token = login_resp.data["token"]
        self.assertTrue(login_resp.data["requires_password_change"])

        change_resp = self.client.post(
            reverse("password-change"),
            {"current_password": "temp1234", "new_password": "brandnew987"},
            format="json",
            HTTP_AUTHORIZATION=f"Token {token}",
        )
        self.assertEqual(change_resp.status_code, status.HTTP_200_OK)
        self.assertNotEqual(change_resp.data["token"], token)
        user.refresh_from_db()
        self.assertFalse(user.must_change_password)

    def test_login_sends_email_notification(self):
        url = reverse("login")
        self.client.post(url, {"username": "shop1", "password": "pass1234"}, format="json")
        self.assertGreaterEqual(len(mail.outbox), 1)
        self.assertIn("Login notification", mail.outbox[0].subject)

    def test_password_change_sends_email_notification(self):
        login_resp = self.client.post(reverse("login"), {"username": "shop1", "password": "pass1234"}, format="json")
        token = login_resp.data["token"]
        mail.outbox.clear()

        resp = self.client.post(
            reverse("password-change"),
            {"current_password": "pass1234", "new_password": "newpass123"},
            format="json",
            HTTP_AUTHORIZATION=f"Token {token}",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(mail.outbox), 1)
        self.assertIn("Password changed", mail.outbox[0].subject)

    def test_forgot_password_sends_email(self):
        resp = self.client.post(reverse("password-forgot"), {"username": "shop1"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(mail.outbox), 1)
        self.assertIn("Password reset requested", mail.outbox[0].subject)

    def test_profile_update_requires_banking_fields(self):
        login_resp = self.client.post(reverse("login"), {"username": "shop1", "password": "pass1234"}, format="json")
        token = login_resp.data["token"]

        resp = self.client.put(
            reverse("shop-profile"),
            {"name": "New Name"},
            format="json",
            HTTP_AUTHORIZATION=f"Token {token}",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("bank_name", resp.data)

    def test_profile_update_marks_completed_and_sends_email(self):
        login_resp = self.client.post(reverse("login"), {"username": "shop1", "password": "pass1234"}, format="json")
        token = login_resp.data["token"]
        mail.outbox.clear()

        payload = {
            "name": "Shop One Updated",
            "contact_phone": "+123456789",
            "contact_email": "shop1@example.com",
            "bank_name": "Bank",
            "bank_account_name": "Shop One",
            "bank_account_number": "1234567890",
        }
        resp = self.client.put(reverse("shop-profile"), payload, format="json", HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["profile_completed"])
        self.assertGreaterEqual(len(mail.outbox), 1)
        self.assertIn("Profile updated", mail.outbox[0].subject)

    def test_reset_confirm_updates_password_and_issues_token(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        resp = self.client.post(
            reverse("password-reset"),
            {"uid": uid, "token": token, "new_password": "brandNewPass1"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("brandNewPass1"))

    def test_login_requires_otp_when_2fa_enabled(self):
        self.user.two_factor_enabled = True
        self.user.ensure_totp_secret()
        self.user.save(update_fields=["two_factor_enabled", "totp_secret"])

        url = reverse("login")
        resp = self.client.post(url, {"username": "shop1", "password": "pass1234"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("otp", resp.data)

        code = pyotp.TOTP(self.user.totp_secret).now()
        resp_ok = self.client.post(
            url,
            {"username": "shop1", "password": "pass1234", "otp": code},
            format="json",
        )
        self.assertEqual(resp_ok.status_code, status.HTTP_200_OK)

    def test_2fa_setup_enable_disable_flow(self):
        login_resp = self.client.post(reverse("login"), {"username": "shop1", "password": "pass1234"}, format="json")
        token = login_resp.data["token"]

        setup_resp = self.client.get(reverse("2fa-setup"), HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(setup_resp.status_code, status.HTTP_200_OK)
        secret = setup_resp.data["secret"]
        self.assertTrue(secret)

        code = pyotp.TOTP(secret).now()
        enable_resp = self.client.post(
            reverse("2fa-enable"),
            {"otp": code},
            format="json",
            HTTP_AUTHORIZATION=f"Token {token}",
        )
        self.assertEqual(enable_resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.two_factor_enabled)

        code2 = pyotp.TOTP(secret).now()
        disable_resp = self.client.post(
            reverse("2fa-disable"),
            {"otp": code2},
            format="json",
            HTTP_AUTHORIZATION=f"Token {token}",
        )
        self.assertEqual(disable_resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertFalse(self.user.two_factor_enabled)
