from handlers.game import _resolve_after_move
from utils.game_logic import EMPTY, apply_timeout, finalize_placements


def game_state(mode: str):
    size = 3 if mode == "classic" else 5
    slots = ["p0", "p1"] if mode == "classic" else ["p0", "p1", "p2"]
    return {
        "mode": mode,
        "board": [[EMPTY for _ in range(size)] for _ in range(size)],
        "slots": slots,
        "turn_idx": 0,
        "placements": {},
        "draw_slots": [],
        "draw_type": None,
    }


def test_classic_win_finishes_with_complete_placements():
    game = game_state("classic")
    game["board"][0] = ["p0", "p0", "p0"]
    assert _resolve_after_move(game, 0, 2, "p0")
    assert game["placements"] == {"p0": 1, "p1": 2}


def test_battle_first_winner_is_removed_and_game_continues():
    game = game_state("battle")
    game["board"][0][:4] = ["p0"] * 4
    assert not _resolve_after_move(game, 0, 3, "p0")
    assert game["placements"] == {"p0": 1}
    assert game["slots"][game["turn_idx"]] == "p1"


def test_existing_battle_line_does_not_award_next_player():
    game = game_state("battle")
    game["board"][0][:4] = ["p0"] * 4
    game["board"][4][4] = "p1"
    game["turn_idx"] = 1
    assert not _resolve_after_move(game, 4, 4, "p1")
    assert "p1" not in game["placements"]


def test_battle_timeout_then_winner_produces_1_2_3_ranks():
    game = game_state("battle")
    apply_timeout(game["slots"], game["placements"], "p2")
    game["placements"]["p0"] = 1
    finalize_placements(game["slots"], game["placements"])
    assert game["placements"] == {"p2": 3, "p0": 1, "p1": 2}
