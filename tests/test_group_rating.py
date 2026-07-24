from unittest.mock import AsyncMock, MagicMock

import pytest

from config import STARTING_RATING
from database import Database
from handlers import commands as command_handler
from handlers import game as game_handler


@pytest.mark.asyncio
async def test_game_result_persists_group_chat_and_rating_delta():
    database = Database()
    pool = MagicMock()
    connection = MagicMock()
    connection.fetchrow = AsyncMock(return_value={"reward": 5_000, "rank": 1, "is_draw": False, "draw_type": None})
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=connection)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    connection.transaction.return_value.__aenter__ = AsyncMock(return_value=None)
    connection.transaction.return_value.__aexit__ = AsyncMock(return_value=None)
    database.pool = pool

    await database.process_game_results(
        "group-game-1",
        "classic",
        [{"user_id": -1, "rank": 1, "is_draw": False, "draw_type": None}],
        chat_id=-1001234567890,
    )

    insert = connection.fetchrow.await_args
    assert "rating_delta, chat_id" in insert.args[0]
    assert insert.args[-2:] == (25, -1001234567890)


@pytest.mark.asyncio
async def test_group_top_query_is_scoped_to_chat_and_uses_group_rating():
    database = Database()
    database.pool = AsyncMock()
    database.pool.fetch.return_value = [
        {
            "user_id": 1,
            "full_name": "Player",
            "rating_points": 1025,
            "games_count": 1,
            "wins": 1,
            "draws": 0,
        }
    ]

    result = await database.get_group_top(-1001234567890, 35)

    assert result[0]["rating_points"] == 1025
    query_call = database.pool.fetch.await_args
    assert "WHERE gr.chat_id = $1" in query_call.args[0]
    assert "SUM(gr.rating_delta)" in query_call.args[0]
    assert query_call.args[1:] == (-1001234567890, STARTING_RATING, 35)


@pytest.mark.asyncio
async def test_top_command_in_group_renders_only_that_group_rating(monkeypatch):
    message = AsyncMock()
    message.chat.type = "supergroup"
    message.chat.id = -1001234567890
    message.chat.title = "Toshkent Players"
    monkeypatch.setattr(
        command_handler.db,
        "get_group_top",
        AsyncMock(
            return_value=[
                {
                    "full_name": "Ali",
                    "rating_points": 1030,
                    "games_count": 3,
                    "wins": 1,
                    "draws": 1,
                }
            ]
        ),
    )

    await command_handler.cmd_top(message)

    command_handler.db.get_group_top.assert_awaited_once_with(-1001234567890, 35)
    text = message.answer.await_args.args[0]
    assert "Toshkent Players" in text
    assert "Faqat shu guruhda" in text
    assert "Ali" in text and "1030 RP" in text
    assert "🎮 3" in text and "🏆 1" in text and "🤝 1" in text


@pytest.mark.asyncio
async def test_top_command_in_private_chat_keeps_global_rating(monkeypatch):
    message = AsyncMock()
    message.chat.type = "private"
    monkeypatch.setattr(
        command_handler.db,
        "get_global_top",
        AsyncMock(return_value=[{"full_name": "Ali", "rating_points": 1100, "balance": 0}]),
    )

    await command_handler.cmd_top(message)

    command_handler.db.get_global_top.assert_awaited_once_with(35)
    assert "GLOBAL TOP 35" in message.answer.await_args.args[0]


def test_only_telegram_group_games_receive_group_rating_scope():
    assert (
        game_handler._group_rating_chat_id({"group_id": -1001234567890, "is_private": False, "is_inline": False})
        == -1001234567890
    )
    assert game_handler._group_rating_chat_id({"group_id": 10, "is_private": True, "is_inline": False}) is None
    assert game_handler._group_rating_chat_id({"group_id": None, "is_private": False, "is_inline": True}) is None
