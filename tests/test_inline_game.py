from unittest.mock import AsyncMock

import pytest
from aiogram import types

from handlers import game as game_handler
from utils.game_logic import EMPTY


def _user(user_id: int, name: str) -> types.User:
    return types.User(id=user_id, is_bot=False, first_name=name, username=name.lower())


@pytest.mark.asyncio
async def test_inline_target_edits_with_inline_message_id_only():
    bot = AsyncMock()
    target = game_handler.GameMessageTarget(inline_message_id="inline-message-1")

    await target.edit(bot, "Yangilandi")

    bot.edit_message_text.assert_awaited_once_with(
        inline_message_id="inline-message-1",
        text="Yangilandi",
        reply_markup=None,
    )


@pytest.mark.asyncio
async def test_inline_query_returns_personal_classic_and_battle_results():
    query = AsyncMock()
    query.from_user = _user(7001, "Creator")

    await game_handler.inline_game_query(query)

    answer = query.answer.await_args
    assert answer.kwargs["cache_time"] == 0
    assert answer.kwargs["is_personal"] is True
    results = answer.kwargs["results"]
    assert [result.title for result in results] == [
        f"🎮 {game_handler.MODES['classic']['name']}",
        f"🎮 {game_handler.MODES['battle']['name']}",
    ]
    assert all(game_handler._parse_inline_result_id(result.id) for result in results)
    assert all(result.reply_markup.inline_keyboard[0][0].callback_data.startswith("inline_join:") for result in results)


@pytest.mark.asyncio
async def test_chosen_inline_result_persists_inline_target_and_updates_message(monkeypatch):
    game_id = "a9a09f0c-421c-4bfb-b8c7-fca220f692aa"
    result = types.ChosenInlineResult(
        result_id=game_handler._inline_result_id("classic", game_id),
        from_user=_user(7002, "Creator"),
        query="",
        inline_message_id="inline-message-2",
    )
    bot = AsyncMock()
    monkeypatch.setattr(game_handler.db, "ensure_user_exists", AsyncMock())
    monkeypatch.setattr(game_handler.db, "save_game", AsyncMock())

    try:
        await game_handler.chosen_inline_game(result, bot)
        stored = game_handler.games[game_id]
    finally:
        game_handler.games.pop(game_id, None)
        game_handler.game_locks.pop(game_id, None)

    assert stored["status"] == "waiting"
    assert stored["is_inline"] is True
    assert stored["targets"] == [{"inline_message_id": "inline-message-2"}]
    game_handler.db.save_game.assert_awaited_once_with(game_id, "waiting", stored)
    assert bot.edit_message_text.await_args.kwargs["inline_message_id"] == "inline-message-2"


@pytest.mark.asyncio
async def test_inline_join_uses_callback_inline_message_target_and_starts_game(monkeypatch):
    game_id = "b9202c48-621f-4fda-ac99-989519cc3451"
    game_handler.games[game_id] = {
        "id": game_id,
        "status": "waiting",
        "mode": "classic",
        "req": 2,
        "players_list": [{"id": 7003, "name": "Creator", "username": "creator"}],
        "creator_id": 7003,
        "chat_name": "Inline chat",
        "is_inline": True,
        "targets": [{"inline_message_id": "inline-message-3"}],
        "created_at": 1,
    }
    call = AsyncMock()
    call.data = f"inline_join:{game_id}"
    call.inline_message_id = "inline-message-3"
    call.from_user = _user(7004, "Opponent")
    bot = AsyncMock()
    monkeypatch.setattr(game_handler.db, "ensure_user_exists", AsyncMock())
    monkeypatch.setattr(game_handler, "start_real_game", AsyncMock())

    try:
        await game_handler.cb_inline_join(call, bot)
        players = list(game_handler.games[game_id]["players_list"])
    finally:
        game_handler.games.pop(game_id, None)
        game_handler.game_locks.pop(game_id, None)

    assert [player["id"] for player in players] == [7003, 7004]
    game_handler.start_real_game.assert_awaited_once_with(bot, prep_id=game_id)
    assert bot.edit_message_text.await_args.kwargs["inline_message_id"] == "inline-message-3"


@pytest.mark.asyncio
async def test_inline_move_updates_the_same_inline_message(monkeypatch):
    game_id = "ca1381df-f485-4c2c-a160-b99e962798cf"
    game_handler.games[game_id] = {
        "id": game_id,
        "status": "active",
        "mode": "classic",
        "board": [[EMPTY for _ in range(3)] for _ in range(3)],
        "players": {
            "p0": {"id": 7005, "name": "First", "visual": "❌"},
            "p1": {"id": 7006, "name": "Second", "visual": "⭕️"},
        },
        "slots": ["p0", "p1"],
        "turn_idx": 0,
        "placements": {},
        "draw_slots": [],
        "draw_type": None,
        "group_id": None,
        "chat_name": "Inline chat",
        "is_private": False,
        "is_inline": True,
        "targets": [{"inline_message_id": "inline-message-4"}],
        "last_move": 1,
        "created_at": 1,
    }
    call = AsyncMock()
    call.data = f"mv:{game_id}:1:1"
    call.inline_message_id = "inline-message-4"
    call.from_user = _user(7005, "First")
    bot = AsyncMock()
    monkeypatch.setattr(game_handler.db, "save_game", AsyncMock())

    try:
        await game_handler.cb_move(call, bot)
        assert game_handler.games[game_id]["board"][1][1] == "p0"
    finally:
        game_handler.games.pop(game_id, None)
        game_handler.game_locks.pop(game_id, None)

    edit = bot.edit_message_text.await_args
    assert edit.kwargs["inline_message_id"] == "inline-message-4"
    assert "chat_id" not in edit.kwargs
    assert "Second" in edit.kwargs["text"]


@pytest.mark.asyncio
async def test_inline_game_result_replaces_the_inline_message(monkeypatch):
    game_id = "d50d0f0c-d769-4332-bc94-303fbf4ae258"
    game_handler.games[game_id] = {
        "id": game_id,
        "status": "active",
        "mode": "classic",
        "board": [
            ["p0", "p0", "p0"],
            [EMPTY, "p1", EMPTY],
            [EMPTY, EMPTY, "p1"],
        ],
        "players": {
            "p0": {"id": 7007, "name": "Winner", "visual": "❌"},
            "p1": {"id": 7008, "name": "Loser", "visual": "⭕️"},
        },
        "slots": ["p0", "p1"],
        "turn_idx": 0,
        "placements": {"p0": 1, "p1": 2},
        "draw_slots": [],
        "draw_type": None,
        "group_id": None,
        "chat_name": "Inline chat",
        "is_private": False,
        "is_inline": True,
        "targets": [{"inline_message_id": "inline-message-5"}],
        "last_move": 1,
        "created_at": 1,
    }
    bot = AsyncMock()
    monkeypatch.setattr(
        game_handler.db,
        "process_game_results",
        AsyncMock(
            return_value={
                "results": [
                    {"user_id": 7007, "rank": 1, "reward": 25, "is_draw": False},
                    {"user_id": 7008, "rank": 2, "reward": -10, "is_draw": False},
                ],
                "referrals": [],
            }
        ),
    )
    monkeypatch.setattr(game_handler.db, "delete_game", AsyncMock())

    try:
        await game_handler.finish_game(bot, game_id)
    finally:
        game_handler.games.pop(game_id, None)
        game_handler.game_locks.pop(game_id, None)

    edit = bot.edit_message_text.await_args
    assert edit.kwargs["inline_message_id"] == "inline-message-5"
    assert "O'YIN YAKUNLANDI" in edit.kwargs["text"]
    assert "G'olib" in edit.kwargs["text"]
    bot.send_message.assert_not_awaited()
