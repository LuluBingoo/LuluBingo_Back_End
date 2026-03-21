from __future__ import annotations

from functools import lru_cache
import random
from typing import Iterable


OFFLINE_CARTELLA_COUNT = 200
OFFLINE_CARTELLA_SEED = 20260306
OFFLINE_CENTER_INDEX = 12
OFFLINE_NUMBER_POOL = tuple(range(1, 76))
OFFLINE_CANDIDATES_PER_BOARD = 48


def _generate_seeded_board(rng: random.Random) -> list[int]:
    values = rng.sample(OFFLINE_NUMBER_POOL, 24)
    rng.shuffle(values)

    board = [0] * 25
    slots = [index for index in range(25) if index != OFFLINE_CENTER_INDEX]
    for slot, value in zip(slots, values):
        board[slot] = value

    return board




@lru_cache(maxsize=1)
def get_offline_cartella_catalog() -> tuple[tuple[int, ...], ...]:
    rng = random.Random(OFFLINE_CARTELLA_SEED)
    boards: list[tuple[int, ...]] = []
    signatures: set[tuple[int, ...]] = set()
    value_signatures: set[tuple[int, ...]] = set()
    attempts = 0
    max_attempts = OFFLINE_CARTELLA_COUNT * 2000

    while len(boards) < OFFLINE_CARTELLA_COUNT:
        attempts += 1
        if attempts > max_attempts:
            raise ValueError("Failed to generate offline cartella catalog")

        board = _generate_seeded_board(rng)
        non_zero_values = [number for number in board if number != 0]
        if len(non_zero_values) != 24 or len(set(non_zero_values)) != 24:
            continue
        if board[OFFLINE_CENTER_INDEX] != 0:
            continue

        signature = tuple(board)
        value_signature = tuple(sorted(non_zero_values))
        if signature in signatures or value_signature in value_signatures:
            continue

        signatures.add(signature)
        value_signatures.add(value_signature)
        boards.append(signature)

    return tuple(boards)


def get_offline_cartella_board(cartella_number: int) -> list[int]:
    if cartella_number < 1 or cartella_number > OFFLINE_CARTELLA_COUNT:
        raise ValueError("Offline cartella number must be between 1 and 200")
    return list(get_offline_cartella_catalog()[cartella_number - 1])