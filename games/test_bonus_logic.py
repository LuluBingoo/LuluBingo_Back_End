from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import ShopUser
from games.models import Game


class BonusGameFlowTests(APITestCase):
    def setUp(self):
        self.shop = ShopUser.objects.create_user(
            username="bonus-shop",
            password="pass12345",
            name="Bonus Shop",
            contact_email="bonus-shop@example.com",
            contact_phone="0911000000",
            status=ShopUser.Status.ACTIVE,
            must_change_password=False,
            wallet_balance=Decimal("500.00"),
            shop_cut_percentage=Decimal("20.00"),
            lulu_cut_percentage=Decimal("50.00"),
        )

    def shop_headers(self):
        login_resp = self.client.post(
            reverse("login"),
            {"username": "bonus-shop", "password": "pass12345"},
            format="json",
        )
        self.assertEqual(login_resp.status_code, status.HTTP_200_OK)
        token = login_resp.data["token"]
        return {"HTTP_AUTHORIZATION": f"Token {token}"}

    def _create_single_cartella_game(self) -> str:
        payload = {
            "bet_amount": "10.00",
            "num_players": 1,
            "win_amount": "20.00",
            "cartella_numbers": [list(range(1, 26))],
        }
        create_resp = self.client.post(
            reverse("games"), payload, format="json", **self.shop_headers()
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        return create_resp.data["game_code"]

    def test_players_funded_bonus_deducts_from_payout_and_awards_pot(self):
        self.shop.bonus_enabled = True
        self.shop.bonus_funding_source = ShopUser.BonusFundingSource.PLAYERS
        self.shop.bonus_contribution_per_cartella = Decimal("1.00")
        self.shop.bonus_min_rounds = 1
        self.shop.bonus_max_rounds = 1
        self.shop.save(
            update_fields=[
                "bonus_enabled",
                "bonus_funding_source",
                "bonus_contribution_per_cartella",
                "bonus_min_rounds",
                "bonus_max_rounds",
            ]
        )

        code = self._create_single_cartella_game()

        claim_resp = self.client.post(
            reverse("game-claim", args=[code]),
            {"cartella_index": 0, "called_numbers": [1, 2, 3, 4, 5]},
            format="json",
            **self.shop_headers(),
        )

        self.assertEqual(claim_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(claim_resp.data["is_bingo"])
        self.assertEqual(claim_resp.data["payout_amount"], "7.00")
        self.assertEqual(claim_resp.data["bonus_contribution_amount"], "1.00")
        self.assertEqual(claim_resp.data["bonus_awarded_amount"], "1.00")
        self.assertEqual(claim_resp.data["bonus_awarded_cartella_index"], 0)

        game = Game.objects.get(game_code=code)
        self.assertEqual(game.bonus_contribution_amount, Decimal("1.00"))
        self.assertEqual(game.bonus_awarded_amount, Decimal("1.00"))
        self.assertEqual(game.bonus_awarded_cartella_index, 0)

        self.shop.refresh_from_db()
        self.assertEqual(self.shop.bonus_pot_balance, Decimal("0.00"))
        self.assertEqual(self.shop.bonus_round_counter, 0)
        self.assertEqual(self.shop.bonus_next_award_round, 1)

    def test_shop_funded_bonus_deducts_from_shop_net_cut_and_awards_pot(self):
        self.shop.bonus_enabled = True
        self.shop.bonus_funding_source = ShopUser.BonusFundingSource.SHOP
        self.shop.bonus_contribution_per_cartella = Decimal("1.00")
        self.shop.bonus_min_rounds = 1
        self.shop.bonus_max_rounds = 1
        self.shop.save(
            update_fields=[
                "bonus_enabled",
                "bonus_funding_source",
                "bonus_contribution_per_cartella",
                "bonus_min_rounds",
                "bonus_max_rounds",
            ]
        )

        code = self._create_single_cartella_game()

        claim_resp = self.client.post(
            reverse("game-claim", args=[code]),
            {"cartella_index": 0, "called_numbers": [1, 2, 3, 4, 5]},
            format="json",
            **self.shop_headers(),
        )

        self.assertEqual(claim_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(claim_resp.data["is_bingo"])
        self.assertEqual(claim_resp.data["payout_amount"], "8.00")
        self.assertEqual(claim_resp.data["shop_net_cut_amount"], "0.00")
        self.assertEqual(claim_resp.data["bonus_contribution_amount"], "1.00")
        self.assertEqual(claim_resp.data["bonus_awarded_amount"], "1.00")
        self.assertEqual(claim_resp.data["bonus_awarded_cartella_index"], 0)

        game = Game.objects.get(game_code=code)
        self.assertEqual(game.bonus_contribution_amount, Decimal("1.00"))
        self.assertEqual(game.bonus_awarded_amount, Decimal("1.00"))
        self.assertEqual(game.bonus_awarded_cartella_index, 0)

        self.shop.refresh_from_db()
        self.assertEqual(self.shop.bonus_pot_balance, Decimal("0.00"))
        self.assertEqual(self.shop.bonus_round_counter, 0)
        self.assertEqual(self.shop.bonus_next_award_round, 1)
