from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import ShopUser
from games.models import Game
from transactions.models import Transaction


class LuluCutGameFlowTests(APITestCase):
    def setUp(self):
        self.shop = ShopUser.objects.create_user(
            username="lulu-shop",
            password="pass12345",
            name="Lulu Cut Shop",
            contact_email="lulu-shop@example.com",
            contact_phone="0911333444",
            status=ShopUser.Status.ACTIVE,
            must_change_password=False,
            wallet_balance=Decimal("500.00"),
            shop_cut_percentage=Decimal("20.00"),
            lulu_cut_percentage=Decimal("50.00"),
        )

    def shop_headers(self):
        login_resp = self.client.post(
            reverse("login"),
            {"username": "lulu-shop", "password": "pass12345"},
            format="json",
        )
        self.assertEqual(login_resp.status_code, status.HTTP_200_OK)
        token = login_resp.data["token"]
        return {"HTTP_AUTHORIZATION": f"Token {token}"}

    def test_create_game_rejects_when_balance_cannot_cover_lulu_cut(self):
        self.shop.wallet_balance = Decimal("0.10")
        self.shop.save(update_fields=["wallet_balance"])

        payload = {
            "bet_amount": "10.00",
            "num_players": 1,
            "win_amount": "20.00",
            "cartella_numbers": [[1, 2, 3, 4, 5]],
        }
        resp = self.client.post(reverse("games"), payload, format="json", **self.shop_headers())

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data.get("error_code"), "insufficient_lulu_cut_balance")
        self.assertEqual(Game.objects.filter(shop=self.shop).count(), 0)

    def test_claim_winner_records_lulu_cut_debit_and_net_cut(self):
        payload = {
            "bet_amount": "10.00",
            "num_players": 1,
            "win_amount": "20.00",
            "cartella_numbers": [list(range(1, 26))],
        }
        create_resp = self.client.post(reverse("games"), payload, format="json", **self.shop_headers())
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        code = create_resp.data["game_code"]

        winning_numbers = [1, 2, 3, 4, 5]
        claim_resp = self.client.post(
            reverse("game-claim", args=[code]),
            {"cartella_index": 0, "called_numbers": winning_numbers},
            format="json",
            **self.shop_headers(),
        )
        self.assertEqual(claim_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(claim_resp.data["is_bingo"])
        self.assertEqual(claim_resp.data["shop_cut_amount"], "2.00")
        self.assertEqual(claim_resp.data["lulu_cut_amount"], "1.00")
        self.assertEqual(claim_resp.data["shop_net_cut_amount"], "1.00")

        game = Game.objects.get(game_code=code)
        self.assertEqual(game.shop_cut_amount, Decimal("2.00"))
        self.assertEqual(game.lulu_cut_amount, Decimal("1.00"))
        self.assertEqual(game.shop_net_cut_amount, Decimal("1.00"))

        self.shop.refresh_from_db()
        self.assertEqual(self.shop.wallet_balance, Decimal("499.00"))

        tx_types = list(Transaction.objects.filter(user=self.shop).values_list("tx_type", flat=True))
        self.assertIn(Transaction.Type.LULU_CUT_DEBIT, tx_types)
        self.assertNotIn(Transaction.Type.BET_DEBIT, tx_types)
        self.assertNotIn(Transaction.Type.BET_CREDIT, tx_types)
