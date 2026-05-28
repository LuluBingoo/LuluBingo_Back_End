# Bonus Summary

## Shop-Level Inputs (Settings)

- `bonus_enabled`: Turns the bonus system on/off for the shop. If false, nothing is contributed or awarded.
- `bonus_funding_source`: Who funds the bonus contribution each game.
  - `players`: Deduct from the winner payout.
  - `shop`: Deduct from the shop net cut.
- `bonus_contribution_per_cartella`: Amount contributed per cartella for each completed game.
- `bonus_min_rounds`: Minimum rounds before a bonus can be awarded.
- `bonus_max_rounds`: Maximum rounds before a bonus must be awarded (random target is bounded by this).
- `bonus_pot_balance`: Rolling bonus pot balance (accumulates contributions).
- `bonus_round_counter`: Number of completed games since last award.
- `bonus_next_award_round`: Random target round; when counter reaches this, the pot is awarded.

## Per-Game Inputs

- `cartella_numbers`: Used to count cartellas in the game.
- `payout_amount`: Current winner payout before bonus deduction (players-funded).
- `shop_net_cut_amount`: Current shop net cut before bonus deduction (shop-funded).
- `winner_cartella_index`: Must exist for an award to be paid.

## Core Calculation Rules

- Contribution = `bonus_contribution_per_cartella` \* cartella count, rounded to cents.
- If funding is `players`, contribution is deducted from `payout_amount` (capped at payout).
- If funding is `shop`, contribution is deducted from `shop_net_cut_amount` (capped at shop net cut).
- If the capped contribution is zero or negative, no bonus changes happen.

## Round / Award Logic

- `bonus_round_counter` increments for every completed game with a contribution.
- `bonus_next_award_round` is randomized between `bonus_min_rounds` and `bonus_max_rounds`.
- If min/max are invalid, min is forced to >= 1 and max is forced to >= min.
- When a winner exists and `bonus_round_counter >= bonus_next_award_round`, the full pot is awarded.
- After award: pot resets to 0, counter resets to 0, and a new random target is set.

## Recorded Outputs

- On the game:
  - `bonus_contribution_amount`
  - `bonus_awarded_amount`
  - `bonus_awarded_cartella_index` (only set if an award happens)
- On the shop:
  - `bonus_pot_balance`
  - `bonus_round_counter`
  - `bonus_next_award_round`
