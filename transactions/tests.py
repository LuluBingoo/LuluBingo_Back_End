from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import ShopUser
from .models import Transaction


class TransactionTests(APITestCase):
    def setUp(self):
        self.user = ShopUser.objects.create_user(
            username="wallet1",
            password="pass1234",
            name="Wallet User",
            contact_email="wallet@example.com",
        )
        self.user.status = ShopUser.Status.ACTIVE
        self.user.must_change_password = False
        self.user.save()

    def auth_headers(self):
        resp = self.client.post(reverse("login"), {"username": "wallet1", "password": "pass1234"}, format="json")
        token = resp.data["token"]
        return {"HTTP_AUTHORIZATION": f"Token {token}"}

    def test_deposit_and_history(self):
        headers = self.auth_headers()
        resp = self.client.post(reverse("tx-deposit"), {"amount": "25.00"}, format="json", **headers)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.user.refresh_from_db()
        self.assertEqual(float(self.user.wallet_balance), 25.00)
        history = self.client.get(reverse("tx-history"), **headers)
        self.assertEqual(history.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(history.data), 1)

    def test_withdraw_requires_funds(self):
        headers = self.auth_headers()
        resp = self.client.post(reverse("tx-withdraw"), {"amount": "10.00"}, format="json", **headers)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_withdraw_after_deposit(self):
        headers = self.auth_headers()
        self.client.post(reverse("tx-deposit"), {"amount": "30.00"}, format="json", **headers)
        resp = self.client.post(reverse("tx-withdraw"), {"amount": "10.00"}, format="json", **headers)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.user.refresh_from_db()
        self.assertEqual(float(self.user.wallet_balance), 20.00)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 2)
