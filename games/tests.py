from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import ShopUser
from .models import Game, ShopBingoSession
from transactions.models import Transaction


class GameTests(APITestCase):
    def setUp(self):
        self.shop = ShopUser.objects.create_user(
            username="shopg",
            password="pass1234",
            name="Game Shop",
            contact_email="shop@example.com",
        )
        self.shop.status = ShopUser.Status.ACTIVE
        self.shop.must_change_password = False
        self.shop.wallet_balance = "500.00"
        self.shop.save()

    def auth_headers(self):
        resp = self.client.post(reverse("login"), {"username": "shopg", "password": "pass1234"}, format="json")
        token = resp.data["token"]
        return {"HTTP_AUTHORIZATION": f"Token {token}"}

    def test_create_game_with_cartellas_limit(self):
        headers = self.auth_headers()
        payload = {
            "bet_amount": "10.00",
            "num_players": 2,
            "win_amount": "100.00",
            "cartella_numbers": [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
        }
        resp = self.client.post(reverse("games"), payload, format="json", **headers)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["num_players"], 2)
        self.assertTrue(resp.data["game_code"])
        self.assertEqual(len(resp.data["draw_sequence"]), 75)
        self.assertEqual(resp.data["status"], Game.Status.ACTIVE)
        self.shop.refresh_from_db()
        self.assertEqual(float(self.shop.wallet_balance), 470.00)

    def test_create_game_requires_sufficient_wallet_balance(self):
        headers = self.auth_headers()
        payload = {
            "bet_amount": "250.00",
            "num_players": 1,
            "win_amount": "300.00",
            "cartella_numbers": [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
        }
        resp = self.client.post(reverse("games"), payload, format="json", **headers)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Game.objects.filter(shop=self.shop).count(), 0)

    def test_cartella_limit_enforced(self):
        headers = self.auth_headers()
        payload = {
            "bet_amount": "5.00",
            "num_players": 1,
            "win_amount": "20.00",
            "cartella_numbers": [[1], [2], [3], [4], [5]],  # exceeds 4 per player
        }
        resp = self.client.post(reverse("games"), payload, format="json", **headers)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_fetch_draw_sequences(self):
        headers = self.auth_headers()
        payload = {
            "bet_amount": "10.00",
            "num_players": 1,
            "win_amount": "50.00",
            "cartella_numbers": [[1, 2, 3]],
        }
        create_resp = self.client.post(reverse("games"), payload, format="json", **headers)
        code = create_resp.data["game_code"]

        draw_resp = self.client.get(reverse("game-draw", args=[code]), **headers)
        self.assertEqual(draw_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(draw_resp.data["draw_sequence"]), 75)
        self.assertEqual(len(draw_resp.data["cartella_draw_sequences"]), 1)

    def test_complete_game(self):
        headers = self.auth_headers()
        payload = {
            "bet_amount": "10.00",
            "num_players": 1,
            "win_amount": "50.00",
            "cartella_numbers": [[1, 2, 3]],
        }
        create_resp = self.client.post(reverse("games"), payload, format="json", **headers)
        code = create_resp.data["game_code"]

        complete_resp = self.client.post(reverse("game-complete", args=[code]), {"status": "completed", "winners": [0]}, format="json", **headers)
        self.assertEqual(complete_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(complete_resp.data["status"], "completed")
        self.assertEqual(complete_resp.data["winners"], [0])
        self.shop.refresh_from_db()
        self.assertEqual(float(self.shop.wallet_balance), 540.00)

    def test_cancel_game_refunds_bet(self):
        headers = self.auth_headers()
        payload = {
            "bet_amount": "20.00",
            "num_players": 1,
            "win_amount": "80.00",
            "cartella_numbers": [[1, 2, 3], [4, 5, 6]],
        }
        create_resp = self.client.post(reverse("games"), payload, format="json", **headers)
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        code = create_resp.data["game_code"]

        cancel_resp = self.client.post(
            reverse("game-complete", args=[code]),
            {"status": "cancelled", "winners": []},
            format="json",
            **headers,
        )
        self.assertEqual(cancel_resp.status_code, status.HTTP_200_OK)
        self.shop.refresh_from_db()
        self.assertEqual(float(self.shop.wallet_balance), 500.00)

    def test_finalize_twice_is_blocked(self):
        headers = self.auth_headers()
        payload = {
            "bet_amount": "10.00",
            "num_players": 1,
            "win_amount": "50.00",
            "cartella_numbers": [[1, 2, 3]],
        }
        create_resp = self.client.post(reverse("games"), payload, format="json", **headers)
        code = create_resp.data["game_code"]
        self.client.post(reverse("game-complete", args=[code]), {"status": "completed", "winners": [0]}, format="json", **headers)
        second_resp = self.client.post(reverse("game-complete", args=[code]), {"status": "cancelled", "winners": []}, format="json", **headers)
        self.assertEqual(second_resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_public_cartella_draw(self):
        headers = self.auth_headers()
        payload = {
            "bet_amount": "10.00",
            "num_players": 1,
            "win_amount": "50.00",
            "cartella_numbers": [[1, 2, 3], [4, 5, 6]],
        }
        create_resp = self.client.post(reverse("games"), payload, format="json", **headers)
        code = create_resp.data["game_code"]

        # public endpoint requires no auth
        cartella_resp = self.client.get(reverse("game-cartella-draw", args=[code, 2]))
        self.assertEqual(cartella_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(cartella_resp.data["cartella_number"], 2)
        self.assertEqual(cartella_resp.data["cartella_numbers"], [4, 5, 6])
        self.assertEqual(len(cartella_resp.data["cartella_draw_sequence"]), 75)

    def test_public_cartella_draw_out_of_range(self):
        headers = self.auth_headers()
        payload = {
            "bet_amount": "10.00",
            "num_players": 1,
            "win_amount": "50.00",
            "cartella_numbers": [[1, 2, 3]],
        }
        create_resp = self.client.post(reverse("games"), payload, format="json", **headers)
        code = create_resp.data["game_code"]

        resp = self.client.get(reverse("game-cartella-draw", args=[code, 5]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_claim_validates_bingo(self):
        headers = self.auth_headers()
        payload = {
            "bet_amount": "10.00",
            "num_players": 1,
            "win_amount": "50.00",
            "cartella_numbers": [list(range(1, 26))],
        }
        create_resp = self.client.post(reverse("games"), payload, format="json", **headers)
        code = create_resp.data["game_code"]

        losing_claim = self.client.post(
            reverse("game-claim", args=[code]),
            {"cartella_index": 0, "called_numbers": [1, 2, 3, 4]},
            format="json",
            **headers,
        )
        self.assertEqual(losing_claim.status_code, status.HTTP_200_OK)
        self.assertFalse(losing_claim.data["is_bingo"])

        winning_numbers = [number for idx, number in enumerate(range(1, 26)) if idx != 12]
        winning_claim = self.client.post(
            reverse("game-claim", args=[code]),
            {"cartella_index": 0, "called_numbers": winning_numbers},
            format="json",
            **headers,
        )
        self.assertEqual(winning_claim.status_code, status.HTTP_200_OK)
        self.assertTrue(winning_claim.data["is_bingo"])
        self.assertEqual(winning_claim.data["required_count"], 24)

    def test_game_transactions_created(self):
        headers = self.auth_headers()
        payload = {
            "bet_amount": "10.00",
            "num_players": 1,
            "win_amount": "50.00",
            "cartella_numbers": [[1, 2, 3]],
        }
        create_resp = self.client.post(reverse("games"), payload, format="json", **headers)
        code = create_resp.data["game_code"]
        self.client.post(reverse("game-complete", args=[code]), {"status": "completed", "winners": [0]}, format="json", **headers)

        tx_types = list(Transaction.objects.filter(user=self.shop).values_list("tx_type", flat=True))
        self.assertIn(Transaction.Type.BET_DEBIT, tx_types)
        self.assertIn(Transaction.Type.BET_CREDIT, tx_types)

    def test_shop_mode_prevents_duplicate_cartella(self):
        headers = self.auth_headers()
        session_resp = self.client.post(
            reverse("shop-mode-session-create"),
            {"min_bet_per_cartella": "20.00"},
            format="json",
            **headers,
        )
        self.assertEqual(session_resp.status_code, status.HTTP_201_CREATED)
        session_id = session_resp.data["session_id"]

        reserve_1 = self.client.post(
            reverse("shop-mode-session-reserve", args=[session_id]),
            {
                "player_name": "Player A",
                "cartella_numbers": [1, 2],
                "bet_per_cartella": "20.00",
            },
            format="json",
            **headers,
        )
        self.assertEqual(reserve_1.status_code, status.HTTP_200_OK)

        reserve_2 = self.client.post(
            reverse("shop-mode-session-reserve", args=[session_id]),
            {
                "player_name": "Player B",
                "cartella_numbers": [2, 3],
                "bet_per_cartella": "20.00",
            },
            format="json",
            **headers,
        )
        self.assertEqual(reserve_2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_shop_mode_creates_game_on_fourth_paid_player(self):
        headers = self.auth_headers()
        session_resp = self.client.post(
            reverse("shop-mode-session-create"),
            {"min_bet_per_cartella": "20.00"},
            format="json",
            **headers,
        )
        self.assertEqual(session_resp.status_code, status.HTTP_201_CREATED)
        session_id = session_resp.data["session_id"]

        players = [
            ("P1", [1, 2, 3, 4]),
            ("P2", [5, 6, 7, 8]),
            ("P3", [9, 10, 11, 12]),
            ("P4", [13, 14, 15, 16]),
        ]

        for player_name, cartellas in players:
            reserve_resp = self.client.post(
                reverse("shop-mode-session-reserve", args=[session_id]),
                {
                    "player_name": player_name,
                    "cartella_numbers": cartellas,
                    "bet_per_cartella": "20.00",
                },
                format="json",
                **headers,
            )
            self.assertEqual(reserve_resp.status_code, status.HTTP_200_OK)

        created_game_code = None
        for player_name, _ in players:
            confirm_resp = self.client.post(
                reverse("shop-mode-session-confirm", args=[session_id]),
                {"player_name": player_name},
                format="json",
                **headers,
            )
            self.assertEqual(confirm_resp.status_code, status.HTTP_200_OK)
            if confirm_resp.data.get("game_created"):
                created_game_code = confirm_resp.data["game"]["game_code"]

        self.assertIsNotNone(created_game_code)
        game = Game.objects.get(game_code=created_game_code)
        self.assertEqual(game.game_mode, Game.Mode.SHOP_FIXED4)
        self.assertEqual(game.num_players, 4)

        session = ShopBingoSession.objects.get(session_id=session_id)
        self.assertEqual(session.status, ShopBingoSession.Status.LOCKED)
        self.assertIsNotNone(session.game)
