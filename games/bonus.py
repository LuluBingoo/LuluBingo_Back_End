from __future__ import annotations

import random
from decimal import Decimal, ROUND_HALF_UP

from accounts.models import ShopUser

from .models import Game


ZERO = Decimal("0")
CENT = Decimal("0.01")


def _to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return ZERO


def _q(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def settle_bonus_for_completed_game(
    *,
    game: Game,
    winner_cartella_index: int | None,
    payout_amount: Decimal,
    shop_net_cut_amount: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Apply per-shop bonus contribution for a completed game.

    Behavior:
    - Collects a per-cartella contribution into a rolling bonus pot.
    - Deducts the contribution from either the winner payout (players-funded)
      or the shop net cut (shop-funded), based on shop configuration.
    - After a random number of rounds (bounded by min/max), awards the entire
      pot to the current game's winner and resets the pot.

    Notes:
    - Must be called within an atomic transaction.
    - Callers should already hold a lock on the Game row.

    Returns updated (payout_amount, shop_net_cut_amount, contribution, awarded_amount).
    Side effects:
    - Locks and updates the ShopUser bonus pot/counters.
    - Sets bonus fields on the provided Game instance.
    """

    # Always reset per-game fields so callers don't accidentally persist stale values.
    game.bonus_contribution_amount = ZERO
    game.bonus_awarded_amount = ZERO
    game.bonus_awarded_cartella_index = None

    shop = ShopUser.objects.select_for_update().get(pk=game.shop_id)

    if not bool(getattr(shop, "bonus_enabled", False)):
        return payout_amount, shop_net_cut_amount, ZERO, ZERO

    per_cartella = _q(_to_decimal(getattr(shop, "bonus_contribution_per_cartella", ZERO)))
    if per_cartella <= ZERO:
        return payout_amount, shop_net_cut_amount, ZERO, ZERO

    cartella_count = len(game.cartella_numbers or [])
    desired = _q(per_cartella * Decimal(cartella_count))
    if desired <= ZERO:
        return payout_amount, shop_net_cut_amount, ZERO, ZERO

    funding_source = str(
        getattr(shop, "bonus_funding_source", ShopUser.BonusFundingSource.PLAYERS)
    )

    contribution = desired

    if funding_source == ShopUser.BonusFundingSource.SHOP:
        if shop_net_cut_amount <= ZERO:
            return payout_amount, shop_net_cut_amount, ZERO, ZERO
        contribution = min(contribution, shop_net_cut_amount)
        contribution = _q(contribution)
        shop_net_cut_amount = _q(shop_net_cut_amount - contribution)
    else:
        if payout_amount <= ZERO:
            return payout_amount, shop_net_cut_amount, ZERO, ZERO
        contribution = min(contribution, payout_amount)
        contribution = _q(contribution)
        payout_amount = _q(payout_amount - contribution)

    if contribution <= ZERO:
        return payout_amount, shop_net_cut_amount, ZERO, ZERO

    pot_before = _q(_to_decimal(shop.bonus_pot_balance))
    pot_after = _q(pot_before + contribution)

    min_rounds = int(getattr(shop, "bonus_min_rounds", 1) or 1)
    max_rounds = int(getattr(shop, "bonus_max_rounds", min_rounds) or min_rounds)
    if min_rounds < 1:
        min_rounds = 1
    if max_rounds < min_rounds:
        max_rounds = min_rounds

    round_counter = int(getattr(shop, "bonus_round_counter", 0) or 0) + 1

    target_round = int(getattr(shop, "bonus_next_award_round", 0) or 0)
    if target_round < min_rounds or target_round > max_rounds:
        target_round = random.randint(min_rounds, max_rounds)

    awarded = ZERO
    if (
        winner_cartella_index is not None
        and pot_after > ZERO
        and round_counter >= target_round
    ):
        awarded = pot_after
        pot_after = ZERO
        round_counter = 0
        target_round = random.randint(min_rounds, max_rounds)

    shop.bonus_pot_balance = pot_after
    shop.bonus_round_counter = round_counter
    shop.bonus_next_award_round = target_round
    shop.save(
        update_fields=[
            "bonus_pot_balance",
            "bonus_round_counter",
            "bonus_next_award_round",
        ]
    )

    game.bonus_contribution_amount = contribution
    game.bonus_awarded_amount = awarded
    game.bonus_awarded_cartella_index = winner_cartella_index if awarded > ZERO else None

    return payout_amount, shop_net_cut_amount, contribution, awarded
