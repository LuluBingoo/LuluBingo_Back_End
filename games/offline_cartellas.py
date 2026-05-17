from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import random
from typing import Iterable


OFFLINE_CARTELLA_COUNT = 200
OFFLINE_CARTELLA_SEED = 20260306
OFFLINE_CENTER_INDEX = 12
OFFLINE_NUMBER_POOL = tuple(range(1, 76))
OFFLINE_CANDIDATES_PER_BOARD = 48


def _load_offline_cartella_catalog_from_file() -> tuple[tuple[int, ...], ...] | None:
    """Load the offline cartella catalog from the precomputed JSON file.

    This avoids expensive runtime catalog generation on cold starts.

    Supported JSON shapes:
    - {"1": [..25..], "2": [..], ...}
    - {"cartellas": {"1": [..], ...}, ...}
    """

    project_root = Path(__file__).resolve().parents[1]
    catalog_path = project_root / "OFFLINE_CARTELLA_CATALOG.json"
    if not catalog_path.exists():
        return None

    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    raw_cartellas = payload.get("cartellas") if isinstance(payload.get("cartellas"), dict) else payload
    if not isinstance(raw_cartellas, dict):
        return None

    def normalize_board(board: object) -> tuple[int, ...] | None:
        if not isinstance(board, list):
            return None
        try:
            normalized = [int(value) for value in board[:25]]
        except Exception:
            return None
        if len(normalized) < 25:
            return None
        normalized[OFFLINE_CENTER_INDEX] = 0
        non_zero = [number for number in normalized if number != 0]
        if len(non_zero) != 24 or len(set(non_zero)) != 24:
            return None
        if any(number < 1 or number > 75 for number in non_zero):
            return None
        return tuple(normalized)

    boards: list[tuple[int, ...]] = []
    for idx in range(1, OFFLINE_CARTELLA_COUNT + 1):
        raw_board = raw_cartellas.get(str(idx))
        normalized_board = normalize_board(raw_board)
        if normalized_board is None:
            return None
        boards.append(normalized_board)

    return tuple(boards)


def _generate_seeded_board(rng: random.Random) -> list[int]:
    values = rng.sample(OFFLINE_NUMBER_POOL, 24)
    rng.shuffle(values)

    board = [0] * 25
    slots = [index for index in range(25) if index != OFFLINE_CENTER_INDEX]
    for slot, value in zip(slots, values):
        board[slot] = value

    return board


def _board_non_zero_values(board: Iterable[int]) -> set[int]:
    return {value for value in board if value != 0}


def _board_rows(board: list[int]) -> list[tuple[int, ...]]:
    return [tuple(board[col * 5 + row] for col in range(5)) for row in range(5)]


def _board_columns(board: list[int]) -> list[tuple[int, ...]]:
    return [tuple(board[col * 5 : (col + 1) * 5]) for col in range(5)]


def _similarity_key(candidate: list[int], existing_boards: list[tuple[int, ...]]) -> tuple[int, ...]:
    if not existing_boards:
        non_zero_values = sorted(value for value in candidate if value != 0)
        return (0, 0, 0, 0, 0, 0, -(non_zero_values[-1] - non_zero_values[0]))

    candidate_values = _board_non_zero_values(candidate)
    candidate_rows = {tuple(sorted(value for value in row if value != 0)) for row in _board_rows(candidate)}
    candidate_columns = {tuple(sorted(value for value in column if value != 0)) for column in _board_columns(candidate)}

    max_value_overlap = 0
    total_value_overlap = 0
    max_position_overlap = 0
    total_position_overlap = 0
    max_structure_overlap = 0
    total_structure_overlap = 0

    for existing in existing_boards:
        existing_list = list(existing)
        existing_values = _board_non_zero_values(existing_list)
        value_overlap = len(candidate_values & existing_values)
        total_value_overlap += value_overlap
        max_value_overlap = max(max_value_overlap, value_overlap)

        position_overlap = sum(
            1
            for index, value in enumerate(candidate)
            if index != OFFLINE_CENTER_INDEX and value == existing_list[index]
        )
        total_position_overlap += position_overlap
        max_position_overlap = max(max_position_overlap, position_overlap)

        existing_rows = {
            tuple(sorted(value for value in row if value != 0))
            for row in _board_rows(existing_list)
        }
        existing_columns = {
            tuple(sorted(value for value in column if value != 0))
            for column in _board_columns(existing_list)
        }
        structure_overlap = len(candidate_rows & existing_rows) + len(candidate_columns & existing_columns)
        total_structure_overlap += structure_overlap
        max_structure_overlap = max(max_structure_overlap, structure_overlap)

    non_zero_values = sorted(candidate_values)
    spread = non_zero_values[-1] - non_zero_values[0]

    return (
        max_value_overlap,
        total_value_overlap,
        max_position_overlap,
        total_position_overlap,
        max_structure_overlap,
        total_structure_overlap,
        -spread,
    )


@lru_cache(maxsize=1)
def get_offline_cartella_catalog() -> tuple[tuple[int, ...], ...]:
    file_catalog = _load_offline_cartella_catalog_from_file()
    if file_catalog is not None:
        return file_catalog

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

        best_candidate: list[int] | None = None
        best_key: tuple[int, ...] | None = None

        for _ in range(OFFLINE_CANDIDATES_PER_BOARD):
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

            candidate_key = _similarity_key(board, boards)
            if best_key is None or candidate_key < best_key:
                best_candidate = board
                best_key = candidate_key

        if best_candidate is None:
            continue

        signature = tuple(best_candidate)
        value_signature = tuple(sorted(number for number in best_candidate if number != 0))
        signatures.add(signature)
        value_signatures.add(value_signature)
        boards.append(signature)

    return tuple(boards)


def get_offline_cartella_board(cartella_number: int) -> list[int]:
    if cartella_number < 1 or cartella_number > OFFLINE_CARTELLA_COUNT:
        raise ValueError("Offline cartella number must be between 1 and 200")
    return list(get_offline_cartella_catalog()[cartella_number - 1])