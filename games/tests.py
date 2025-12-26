from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import ShopUser
from .models import Game


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
