from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import ShopUser, LoginAttempt


class AuthTests(APITestCase):
    def setUp(self):
        self.user = ShopUser.objects.create_user(username="shop1", password="pass1234")

    def test_login_success_and_attempt_logged(self):
        url = reverse("login")
        resp = self.client.post(url, {"username": "shop1", "password": "pass1234"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("token", resp.data)
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
