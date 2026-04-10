from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import ShopUser
from transactions.models import Transaction


class AdminEndpointTests(APITestCase):
    def setUp(self):
        self.manager = ShopUser.objects.create_user(
            username="manager1",
            password="pass12345",
            name="Manager One",
            contact_email="manager1@example.com",
            contact_phone="0911001001",
            role=ShopUser.Role.MANAGER,
            status=ShopUser.Status.ACTIVE,
            must_change_password=False,
        )

    def manager_headers(self):
        login_resp = self.client.post(
            reverse("login"),
            {"username": "manager1", "password": "pass12345"},
            format="json",
        )
        self.assertEqual(login_resp.status_code, status.HTTP_200_OK)
        token = login_resp.data["token"]
        return {"HTTP_AUTHORIZATION": f"Token {token}"}

    def test_manager_can_create_shop_with_initial_balance_transaction(self):
        payload = {
            "username": "shop-admin-created",
            "password": "ShopPass123",
            "name": "Admin Created Shop",
            "contact_phone": "0911223344",
            "contact_email": "shop-admin-created@example.com",
            "shop_cut_percentage": "15.00",
            "lulu_cut_percentage": "20.00",
            "initial_balance": "1000.00",
        }

        resp = self.client.post(reverse("admin-shops"), payload, format="json", **self.manager_headers())
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("shop", resp.data)
        self.assertIn("initial_transaction", resp.data)

        shop = ShopUser.objects.get(username="shop-admin-created")
        self.assertEqual(shop.role, ShopUser.Role.SHOP)
        self.assertEqual(shop.wallet_balance, Decimal("1000.00"))
        self.assertEqual(shop.shop_cut_percentage, Decimal("15.00"))
        self.assertEqual(shop.lulu_cut_percentage, Decimal("20.00"))

        initial_tx = Transaction.objects.filter(user=shop).latest("created_at")
        self.assertEqual(initial_tx.tx_type, Transaction.Type.DEPOSIT)
        self.assertEqual(initial_tx.amount, Decimal("1000.00"))
        self.assertEqual(initial_tx.metadata.get("event"), "shop_creation_initial_money")

    def test_manager_can_create_another_manager(self):
        payload = {
            "username": "manager2",
            "password": "ManagerPass123",
            "name": "Manager Two",
            "contact_phone": "0911002002",
            "contact_email": "manager2@example.com",
            "status": ShopUser.Status.ACTIVE,
        }

        resp = self.client.post(reverse("admin-managers"), payload, format="json", **self.manager_headers())
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        manager = ShopUser.objects.get(username="manager2")
        self.assertEqual(manager.role, ShopUser.Role.MANAGER)
        self.assertTrue(manager.is_staff)

    def test_non_manager_cannot_access_admin_shop_creation(self):
        shop_user = ShopUser.objects.create_user(
            username="shop-non-admin",
            password="pass12345",
            name="Non Admin Shop",
            contact_email="non-admin@example.com",
            contact_phone="0911999888",
            role=ShopUser.Role.SHOP,
            status=ShopUser.Status.ACTIVE,
            must_change_password=False,
        )

        login_resp = self.client.post(
            reverse("login"),
            {"username": "shop-non-admin", "password": "pass12345"},
            format="json",
        )
        self.assertEqual(login_resp.status_code, status.HTTP_200_OK)

        payload = {
            "username": "illegal-shop-create",
            "password": "ShopPass123",
            "name": "Illegal Shop",
            "contact_phone": "0911444555",
            "contact_email": "illegal-shop@example.com",
            "shop_cut_percentage": "10.00",
            "lulu_cut_percentage": "10.00",
            "initial_balance": "100.00",
        }

        resp = self.client.post(
            reverse("admin-shops"),
            payload,
            format="json",
            HTTP_AUTHORIZATION=f"Token {login_resp.data['token']}",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(shop_user.role, ShopUser.Role.SHOP)

    def test_manager_can_fill_shop_balance(self):
        shop = ShopUser.objects.create_user(
            username="topup-shop",
            password="pass12345",
            name="Topup Shop",
            contact_email="topup-shop@example.com",
            contact_phone="0911777888",
            role=ShopUser.Role.SHOP,
            status=ShopUser.Status.ACTIVE,
            must_change_password=False,
        )

        resp = self.client.post(
            reverse("admin-shop-fill-balance", args=[shop.id]),
            {"amount": "250.00", "reference": "manual topup"},
            format="json",
            **self.manager_headers(),
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("shop", resp.data)
        self.assertIn("transaction", resp.data)

        shop.refresh_from_db()
        self.assertEqual(shop.wallet_balance, Decimal("250.00"))

        tx = Transaction.objects.filter(user=shop).latest("created_at")
        self.assertEqual(tx.tx_type, Transaction.Type.DEPOSIT)
        self.assertEqual(tx.amount, Decimal("250.00"))
        self.assertEqual(tx.metadata.get("event"), "shop_balance_topup")
