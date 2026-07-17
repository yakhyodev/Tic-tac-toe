from utils.game_logic import (
    EMPTY,
    apply_timeout,
    finalize_placements,
    get_robot_move,
    is_board_full,
    is_winning_move,
)


def empty_board(size: int):
    return [[EMPTY for _ in range(size)] for _ in range(size)]


def test_classic_row_win_uses_logical_slot():
    board = empty_board(3)
    board[1] = ["p0", "p0", "p0"]
    assert is_winning_move(board, 1, 2, "p0", 3)


def test_battle_old_winner_does_not_make_current_player_winner():
    board = empty_board(5)
    board[0][:4] = ["p0"] * 4
    board[4][4] = "p1"
    assert is_winning_move(board, 0, 3, "p0", 4)
    assert not is_winning_move(board, 4, 4, "p1", 4)


def test_battle_diagonal_win():
    board = empty_board(5)
    for index in range(4):
        board[index][4 - index] = "p2"
    assert is_winning_move(board, 3, 1, "p2", 4)


def test_robot_wins_before_blocking():
    board = empty_board(3)
    board[0] = ["robot", "robot", EMPTY]
    board[1] = ["human", "human", EMPTY]
    assert get_robot_move(board, 3, 3, "robot", ["human"]) == (0, 2)


def test_timeout_rank_and_remaining_rank():
    slots = ["p0", "p1", "p2"]
    placements = apply_timeout(slots, {}, "p2")
    assert placements == {"p2": 3}
    placements["p0"] = 1
    assert finalize_placements(slots, placements) == {"p2": 3, "p0": 1, "p1": 2}


def test_board_full():
    assert is_board_full([["p0", "p1"], ["p1", "p0"]])
    assert not is_board_full([["p0", EMPTY], ["p1", "p0"]])
