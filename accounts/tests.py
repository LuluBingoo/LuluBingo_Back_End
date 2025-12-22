from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import ShopUser, LoginAttempt


class AuthTests(APITestCase):
    def setUp(self):
        self.user = ShopUser.objects.create_user(username="shop1", password="pass1234", name="Shop One")
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
        user = ShopUser.objects.create_user(username="shop2", password="temp1234", name="Shop Two")
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
