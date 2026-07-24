from unittest.mock import AsyncMock

import pytest
from aiogram import types

from handlers import game as game_handler
from handlers.commands import cmd_start


def test_group_message_url_targets_exact_public_or_private_message():
    assert game_handler._group_message_url(-1001234567890, 42, "public_group") == "https://t.me/public_group/42"
    assert game_handler._group_message_url(-1001234567890, 42) == "https://t.me/c/1234567890/42"
    assert game_handler._group_message_url(-123456789, 42) is None


@pytest.mark.asyncio
async def test_deep_link_joins_waiting_game_and_returns_to_same_message(monkeypatch):
    game_id = "7e99ff4e-525b-451b-9d6c-273f2797249a"
    waiting_game = {
        "id": game_id,
        "status": "waiting",
        "mode": "battle",
        "req": 3,
        "players_list": [{"id": 1, "name": "Creator", "username": "creator"}],
        "creator_id": 1,
        "group_id": -1001234567890,
        "group_username": None,
        "main_msg_id": 42,
        "bot_username": "tic_tac_toe_bot",
        "chat_name": "Test group",
        "created_at": 1,
    }
    game_handler.games[game_id] = waiting_game
    bot = AsyncMock()
    monkeypatch.setattr(game_handler.db, "ensure_user_exists", AsyncMock(return_value=True))
    monkeypatch.setattr(game_handler.db, "save_game", AsyncMock())
    user = types.User(id=2, is_bot=False, first_name="Player", username="player")

    try:
        result = await game_handler.join_group_game_from_start(bot, user, game_id)
    finally:
        game_handler.games.pop(game_id, None)
        game_handler.game_locks.pop(game_id, None)

    assert result == {
        "success": True,
        "message": "✅ Siz o'yinga qo'shildingiz, omad!",
        "return_url": "https://t.me/c/1234567890/42",
    }
    assert [player["id"] for player in waiting_game["players_list"]] == [1, 2]
    edit = bot.edit_message_text.await_args
    assert edit.kwargs["chat_id"] == -1001234567890
    assert edit.kwargs["message_id"] == 42
    assert edit.kwargs["reply_markup"].inline_keyboard[0][0].url == f"https://t.me/tic_tac_toe_bot?start=join_{game_id}"


@pytest.mark.asyncio
async def test_start_payload_sends_join_confirmation_with_group_button(monkeypatch):
    game_id = "7e99ff4e-525b-451b-9d6c-273f2797249a"
    user = types.User(id=2, is_bot=False, first_name="Player", username="player")
    message = AsyncMock()
    message.from_user = user
    message.text = f"/start join_{game_id}"
    message.chat.type = "private"
    bot = AsyncMock()
    bot.get_me.return_value = types.User(
        id=100,
        is_bot=True,
        first_name="Tic Tac Toe",
        username="tic_tac_toe_bot",
    )
    monkeypatch.setattr(game_handler.db, "register_user", AsyncMock(return_value=True))
    monkeypatch.setattr(
        game_handler,
        "join_group_game_from_start",
        AsyncMock(
            return_value={
                "success": True,
                "message": "✅ Siz o'yinga qo'shildingiz, omad!",
                "return_url": "https://t.me/c/1234567890/42",
            }
        ),
    )

    await cmd_start(message, bot)

    game_handler.db.register_user.assert_awaited_once_with(
        user.id,
        user.username,
        user.full_name,
        None,
        bot_started=True,
    )
    game_handler.join_group_game_from_start.assert_awaited_once_with(bot, user, game_id)
    answer = message.answer.await_args
    assert answer.args[0] == "✅ Siz o'yinga qo'shildingiz, omad!"
    assert answer.kwargs["reply_markup"].inline_keyboard[0][0].url == "https://t.me/c/1234567890/42"
