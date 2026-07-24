from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    ErrorEvent,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from config import Settings
from database import db
from handlers import commands, game

settings = Settings.from_env()
watchdog_task: asyncio.Task | None = None

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot) -> None:
    global watchdog_task
    await db.connect(settings.database_url)
    await db.migrate()
    await db.init_static_data()
    restored = await game.restore_persisted_games()
    logger.info("Tiklangan ochiq o'yinlar: %s", restored)
    for game_id, restored_game in list(game.games.items()):
        if restored_game.get("status") == "active":
            await game.update_ui(bot, game_id)

    private_commands = [
        BotCommand(command="start", description="Botni boshlash"),
        BotCommand(command="game", description="Raqib izlash"),
        BotCommand(command="cancel", description="Navbat/o'yinni bekor qilish"),
        BotCommand(command="profile", description="Profil va reyting"),
        BotCommand(command="shop", description="Skinlar do'koni"),
        BotCommand(command="skins", description="Inventar"),
        BotCommand(command="ref", description="Do'stlarni taklif qilish"),
        BotCommand(command="top", description="Global reyting"),
        BotCommand(command="rules", description="O'yin qoidalari"),
        BotCommand(command="help", description="Yordam"),
    ]
    group_commands = [
        BotCommand(command="game", description="O'yin boshlash"),
        BotCommand(command="cancel", description="O'yinni bekor qilish"),
        BotCommand(command="top", description="Global reyting"),
        BotCommand(command="rules", description="O'yin qoidalari"),
    ]
    await bot.set_my_commands(private_commands, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())
    await bot.set_webhook(
        url=settings.webhook_url,
        secret_token=settings.webhook_secret,
        drop_pending_updates=False,
        allowed_updates=["message", "callback_query", "inline_query", "chosen_inline_result"],
    )
    watchdog_task = asyncio.create_task(game.game_watchdog(bot), name="game-watchdog")
    logger.info("Webhook o'rnatildi: %s", settings.webhook_url)


async def on_shutdown() -> None:
    global watchdog_task
    if watchdog_task:
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass
        watchdog_task = None
    # Webhook ataylab o'chirilmaydi: deploylar orasida update yo'qolmaydi.
    await db.close()
    logger.info("Ilova xavfsiz to'xtatildi")


async def health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "environment": settings.environment})


async def ready(_: web.Request) -> web.Response:
    is_ready = await db.ping()
    return web.json_response(
        {"status": "ready" if is_ready else "not_ready"},
        status=200 if is_ready else 503,
    )


async def handle_dispatcher_error(event: ErrorEvent) -> bool:
    error = event.exception
    logger.error(
        "Telegram update qayta ishlashda xato: %s",
        error,
        exc_info=(type(error), error, error.__traceback__),
    )
    return True


def create_app() -> web.Application:
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()

    # Aniq menyu/buyruqlar catch-all o'yin messengeridan oldin turadi.
    dispatcher.include_router(commands.router)
    dispatcher.include_router(game.router)
    dispatcher.errors.register(handle_dispatcher_error)
    dispatcher.startup.register(on_startup)
    dispatcher.shutdown.register(on_shutdown)

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_get("/ready", ready)
    SimpleRequestHandler(
        dispatcher=dispatcher,
        bot=bot,
        secret_token=settings.webhook_secret,
        handle_in_background=True,
    ).register(app, path=settings.webhook_path)
    setup_application(app, dispatcher, bot=bot)
    return app


def main() -> None:
    web.run_app(create_app(), host=settings.host, port=settings.port)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi")
