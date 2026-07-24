from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import types

from database import Database
from handlers import commands as command_handler


@pytest.mark.asyncio
async def test_start_in_group_does_not_enable_private_messages(monkeypatch):
    user = types.User(id=10, is_bot=False, first_name="Player", username="player")
    message = AsyncMock()
    message.from_user = user
    message.text = "/start"
    message.chat.type = "group"
    bot = AsyncMock()
    bot.get_me.return_value = types.User(id=100, is_bot=True, first_name="Bot", username="game_bot")
    monkeypatch.setattr(command_handler.db, "register_user", AsyncMock())

    await command_handler.cmd_start(message, bot)

    command_handler.db.register_user.assert_awaited_once_with(
        user.id,
        user.username,
        user.full_name,
        None,
        bot_started=False,
    )


@pytest.mark.asyncio
async def test_private_result_recipients_include_only_users_who_started_bot():
    database = Database()
    database.pool = AsyncMock()
    database.pool.fetch.return_value = [{"id": 20}]

    recipients = await database.get_private_message_user_ids([30, -1, 20, 20])

    assert recipients == {20}
    query = database.pool.fetch.await_args
    assert "bot_started = TRUE" in query.args[0]
    assert "is_robot = FALSE" in query.args[0]
    assert query.args[1] == [20, 30]


@pytest.mark.asyncio
async def test_game_result_updates_wallet_and_rating_for_inline_player():
    database = Database()
    pool = MagicMock()
    connection = MagicMock()
    connection.fetchrow = AsyncMock(
        side_effect=[
            {
                "reward": 5_000,
                "rank": 1,
                "is_draw": False,
                "draw_type": None,
                "rating_delta": 25,
            },
            None,
        ]
    )
    connection.execute = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=connection)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    connection.transaction.return_value.__aenter__ = AsyncMock(return_value=None)
    connection.transaction.return_value.__aexit__ = AsyncMock(return_value=None)
    database.pool = pool

    settlement = await database.process_game_results(
        "inline-game-1",
        "classic",
        [{"user_id": 42, "rank": 1, "is_draw": False, "draw_type": None}],
        chat_id=None,
    )

    balance_update = next(
        call
        for call in connection.execute.await_args_list
        if "UPDATE balances" in call.args[0] and "rating_points" in call.args[0]
    )
    assert balance_update.args[1:] == (5_000, 25, 42)
    assert settlement["results"][0]["reward"] == 5_000
    assert settlement["results"][0]["rating_delta"] == 25
