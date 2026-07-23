"""Telegramdan mustaqil Tic-Tac-Toe o'yin qoidalari.

Doska UI emojilarini emas, o'yinchi slotlarini (``p0``, ``p1``...) saqlaydi.
Bu skinni almashtirish o'yin natijasiga ta'sir qilmasligini ta'minlaydi.
"""

from __future__ import annotations

import random
from collections.abc import Iterable

EMPTY = None
rng = random.SystemRandom()


def get_empty_cells(board: list[list[str | None]], size: int | None = None) -> list[tuple[int, int]]:
    board_size = size or len(board)
    return [(row, column) for row in range(board_size) for column in range(board_size) if board[row][column] is EMPTY]


def _count_direction(
    board: list[list[str | None]],
    row: int,
    column: int,
    row_step: int,
    column_step: int,
    player_slot: str,
) -> int:
    size = len(board)
    count = 0
    row += row_step
    column += column_step
    while 0 <= row < size and 0 <= column < size and board[row][column] == player_slot:
        count += 1
        row += row_step
        column += column_step
    return count


def is_winning_move(
    board: list[list[str | None]],
    row: int,
    column: int,
    player_slot: str,
    win_length: int,
) -> bool:
    """Faqat oxirgi yurish yaratgan chiziqni tekshiradi."""
    if board[row][column] != player_slot:
        return False

    for row_step, column_step in ((0, 1), (1, 0), (1, 1), (1, -1)):
        length = 1
        length += _count_direction(board, row, column, row_step, column_step, player_slot)
        length += _count_direction(board, row, column, -row_step, -column_step, player_slot)
        if length >= win_length:
            return True
    return False


def check_winner(
    board: list[list[str | None]],
    size: int,
    win_len: int,
) -> str | None:
    """Moslik uchun umumiy tekshiruv; yangi oqim ``is_winning_move``dan foydalanadi."""
    for row in range(size):
        for column in range(size):
            slot = board[row][column]
            if slot is not EMPTY and is_winning_move(board, row, column, slot, win_len):
                return slot
    return "Draw" if not get_empty_cells(board, size) else None


def is_board_full(board: list[list[str | None]]) -> bool:
    return not any(cell is EMPTY for row in board for cell in row)


def _would_win(
    board: list[list[str | None]],
    row: int,
    column: int,
    slot: str,
    win_length: int,
) -> bool:
    board[row][column] = slot
    try:
        return is_winning_move(board, row, column, slot, win_length)
    finally:
        board[row][column] = EMPTY


def get_robot_move(
    board: list[list[str | None]],
    size: int,
    win_len: int,
    robot_symbol: str,
    active_opponents: Iterable[str] | None = None,
) -> tuple[int, int] | None:
    """Yutish, raqibni bloklash, markaz va tasodifiy yurish strategiyasi."""
    empty_cells = get_empty_cells(board, size)
    if not empty_cells:
        return None

    for row, column in empty_cells:
        if _would_win(board, row, column, robot_symbol, win_len):
            return row, column

    opponents = set(active_opponents or ())
    if not opponents:
        opponents = {cell for board_row in board for cell in board_row if cell is not EMPTY and cell != robot_symbol}

    for opponent in opponents:
        if opponent == robot_symbol:
            continue
        for row, column in empty_cells:
            if _would_win(board, row, column, opponent, win_len):
                return row, column

    center = size // 2
    if (center, center) in empty_cells:
        return center, center

    corners = [cell for cell in ((0, 0), (0, size - 1), (size - 1, 0), (size - 1, size - 1)) if cell in empty_cells]
    return rng.choice(corners or empty_cells)


def is_game_over(board: list[list[str | None]], active_players_count: int) -> bool:
    return active_players_count <= 1 or is_board_full(board)


def next_available_rank(placements: dict[str, int], player_count: int) -> int:
    used = set(placements.values())
    return next(rank for rank in range(1, player_count + 1) if rank not in used)


def apply_timeout(
    slots: list[str],
    placements: dict[str, int],
    timed_out_slot: str,
) -> dict[str, int]:
    """Taymaut qilgan o'yinchiga eng past bo'sh o'rinni atomar modelda beradi."""
    if timed_out_slot in placements:
        return placements
    used = set(placements.values())
    lowest_available = next(rank for rank in range(len(slots), 0, -1) if rank not in used)
    placements[timed_out_slot] = lowest_available
    return placements


def finalize_placements(
    slots: list[str],
    placements: dict[str, int],
) -> dict[str, int]:
    """Bitta faol o'yinchi qolsa unga eng yuqori bo'sh o'rinni beradi."""
    remaining = [slot for slot in slots if slot not in placements]
    if len(remaining) == 1:
        placements[remaining[0]] = next_available_rank(placements, len(slots))
    return placements
