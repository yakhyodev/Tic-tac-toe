from handlers import game as game_handler
from handlers.game import _format_result_lines, _select_player_visuals


def _game(mode, players, slots=None, draw_slots=None):
    ordered_slots = slots or list(players)
    return {
        "mode": mode,
        "slots": ordered_slots,
        "players": players,
        "placements": {},
        "draw_slots": draw_slots or [],
    }


def test_classic_result_orders_winner_before_loser_and_uses_labels():
    game = _game(
        "classic",
        {
            "p0": {"id": 10, "name": "Loser", "visual": "⭕️"},
            "p1": {"id": 20, "name": "Winner", "visual": "❌"},
        },
    )
    lines = _format_result_lines(
        game,
        {
            10: {"rank": 2, "reward": 0, "is_draw": False},
            20: {"rank": 1, "reward": 5_000, "is_draw": False},
        },
    )

    assert "Winner" in lines[0] and "G'olib" in lines[0]
    assert "Loser" in lines[1] and "Mag'lub" in lines[1]
    assert all("o'rin" not in line for line in lines)


def test_battle_result_is_sorted_by_rank_not_slot_order():
    game = _game(
        "battle",
        {
            "p0": {"id": 10, "name": "Third", "visual": "△"},
            "p1": {"id": 20, "name": "First", "visual": "❌"},
            "p2": {"id": 30, "name": "Second", "visual": "⭕️"},
        },
        slots=["p0", "p2", "p1"],
    )
    lines = _format_result_lines(
        game,
        {
            10: {"rank": 3, "reward": 0, "is_draw": False},
            20: {"rank": 1, "reward": 10_000, "is_draw": False},
            30: {"rank": 2, "reward": 5_000, "is_draw": False},
        },
    )

    assert "First" in lines[0] and "1-o'rin" in lines[0]
    assert "Second" in lines[1] and "2-o'rin" in lines[1]
    assert "Third" in lines[2] and "3-o'rin" in lines[2]


def test_tied_players_are_grouped_without_numeric_places():
    game = _game(
        "battle",
        {
            "p0": {"id": 10, "name": "Winner", "visual": "❌"},
            "p1": {"id": 20, "name": "Olma", "visual": "🍎"},
            "p2": {"id": 30, "name": "Anor", "visual": "🍐"},
        },
        draw_slots=["p1", "p2"],
    )
    lines = _format_result_lines(
        game,
        {
            10: {"rank": 1, "reward": 10_000, "is_draw": False},
            20: {"rank": 2, "reward": 700, "is_draw": True},
            30: {"rank": 2, "reward": 700, "is_draw": True},
        },
    )

    assert "1-o'rin" in lines[0]
    assert "🍎 Olma — 🍐 Anor" in lines[1]
    assert "Durrang" in lines[1] and "har biriga" in lines[1]
    assert "2-o'rin" not in lines[1] and "3-o'rin" not in lines[1]


def test_full_draw_has_no_numeric_places():
    game = _game(
        "classic",
        {
            "p0": {"id": 10, "name": "Olma", "visual": "🍎"},
            "p1": {"id": 20, "name": "Anor", "visual": "🍐"},
        },
        draw_slots=["p0", "p1"],
    )
    lines = _format_result_lines(
        game,
        {
            10: {"rank": 99, "reward": 500, "is_draw": True},
            20: {"rank": 99, "reward": 500, "is_draw": True},
        },
    )

    assert len(lines) == 1
    assert "🍎 Olma — 🍐 Anor" in lines[0]
    assert "Durrang" in lines[0]
    assert "o'rin" not in lines[0]


def test_triangle_is_used_only_when_no_battle_player_has_a_skin():
    assert _select_player_visuals("battle", [None, None, None]) == ["❌", "⭕️", "△"]
    assert _select_player_visuals("battle", ["🍎", None, None]) == ["🍎", "❌", "⭕️"]
    assert _select_player_visuals("battle", [None, None, "🍎"]) == ["❌", "⭕️", "🍎"]
    assert "△" not in _select_player_visuals("battle", ["🍎", "🍎", None])


def test_first_turn_uses_random_source(monkeypatch):
    class StubRandom:
        @staticmethod
        def randrange(player_count):
            assert player_count == 3
            return 2

    monkeypatch.setattr(game_handler, "rng", StubRandom())
    assert game_handler._random_turn_index(3) == 2
