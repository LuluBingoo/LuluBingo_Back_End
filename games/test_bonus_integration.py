from decimal import Decimal

from django.test import TestCase

from accounts.models import ShopUser
from .models import Game
from .bonus import settle_bonus_for_completed_game


class BonusIntegrationTests(TestCase):
    def test_players_funded_awards_pot_and_contribution(self):
        shop = ShopUser.objects.create_user(
            username="shop_players",
            password="pass1234",
            contact_email="shop_players@example.local",
            contact_phone="912345678",
            bonus_enabled=True,
            bonus_funding_source=ShopUser.BonusFundingSource.PLAYERS,
            bonus_contribution_per_cartella=Decimal("1.00"),
            bonus_min_rounds=1,
            bonus_max_rounds=1,
            bonus_pot_balance=Decimal("5.00"),
        )

        game = Game.objects.create(
            shop=shop,
            bet_amount=Decimal("10.00"),
            num_players=4,
            win_amount=Decimal("50.00"),
            cartella_numbers=[[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16]],
            payout_amount=Decimal("100.00"),
            shop_net_cut_amount=Decimal("10.00"),
        )

        payout, shop_net, contribution, awarded = settle_bonus_for_completed_game(
            game=game,
            winner_cartella_index=0,
            payout_amount=game.payout_amount,
            shop_net_cut_amount=game.shop_net_cut_amount,
        )

        # contribution should be 4 cartellas * 1.00
        self.assertEqual(contribution, Decimal("4.00"))
        # payout should be reduced by contribution
        self.assertEqual(payout, Decimal("96.00"))
        # awarded should equal previous pot + contribution (5 + 4)
        self.assertEqual(awarded, Decimal("9.00"))

        shop.refresh_from_db()
        game.refresh_from_db()
        self.assertEqual(shop.bonus_pot_balance, Decimal("0.00"))
        self.assertEqual(game.bonus_contribution_amount, contribution)
        self.assertEqual(game.bonus_awarded_amount, awarded)

    def test_shop_funded_deducts_shop_cut_and_awards(self):
        shop = ShopUser.objects.create_user(
            username="shop_funded",
            password="pass1234",
            contact_email="shop_funded@example.local",
            contact_phone="911111111",
            bonus_enabled=True,
            bonus_funding_source=ShopUser.BonusFundingSource.SHOP,
            bonus_contribution_per_cartella=Decimal("2.50"),
            bonus_min_rounds=1,
            bonus_max_rounds=1,
            bonus_pot_balance=Decimal("0.00"),
        )

        game = Game.objects.create(
            shop=shop,
            bet_amount=Decimal("10.00"),
            num_players=2,
            win_amount=Decimal("30.00"),
            cartella_numbers=[[1, 2, 3], [4, 5, 6]],
            payout_amount=Decimal("50.00"),
            shop_net_cut_amount=Decimal("5.00"),
        )

        payout, shop_net, contribution, awarded = settle_bonus_for_completed_game(
            game=game,
            winner_cartella_index=1,
            payout_amount=game.payout_amount,
            shop_net_cut_amount=game.shop_net_cut_amount,
        )

        # contribution should be min(desired=2*2.50=5.00, shop_net_cut=5.00)
        self.assertEqual(contribution, Decimal("5.00"))
        # shop_net_cut should be reduced to zero
        self.assertEqual(shop_net, Decimal("0.00"))
        # awarded equals pot_before(0) + contribution
        self.assertEqual(awarded, Decimal("5.00"))

        shop.refresh_from_db()
        game.refresh_from_db()
        self.assertEqual(shop.bonus_pot_balance, Decimal("0.00"))
        self.assertEqual(game.bonus_contribution_amount, contribution)
        self.assertEqual(game.bonus_awarded_amount, awarded)
