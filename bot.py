import asyncio
import logging
import sys
import os  # Render PORTni aniqlash uchun qo'shildi
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# Bo'lim 1: Loyiha modullarini import qilish
from config import BOT_TOKEN, WEBHOOK_URL
from handlers import commands, game
from database import db
from handlers.game import game_watchdog

# Qism 1.1: Loglarni sozlash
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# --- BO'LIM 2: STARTUP VA SHUTDOWN JARAYONLARI ---

async def on_startup(bot: Bot):
    """
    Bot ishga tushganda bajariladigan amallar
    """
    # 2.1.2: Bazani tekshirish va jadvallarni yaratish
    db.create_tables()
    logging.info("✅ Ma'lumotlar bazasi jadvallari tekshirildi.")

    # 2.1.3: Robotlarni bazaga kiritish
    db.init_static_data()
    logging.info("🤖 Robotlar bazada tekshirildi.")

    # Qism 2.2: Watchdog (Kuzatuvchi) tizimini ishga tushirish
    asyncio.create_task(game_watchdog(bot))
    logging.info("🚀 Watchdog tizimi orqa fonda ishga tushdi.")

    # 2.1.4: Telegram menyu buyruqlarini sozlash
    private_commands = [
        BotCommand(command="start", description="🔄 Botni yangilash"),
        BotCommand(command="game", description="🎮 Raqib izlash (Matchmaking)"),
        BotCommand(command="ref", description="🤝 Do'stlarni taklif qilish (50,000 so'm)"),
        BotCommand(command="stat", description="👤 Profil va Moneta ($)"),
        BotCommand(command="shop", description="🛒 Skinlar do'koni"),
        BotCommand(command="skinlar", description="🎨 Mening mevalarim (Inventar)"),
        BotCommand(command="global", description="🏆 Global Top 35 reyting")
    ]
    
    group_commands = [
        BotCommand(command="game", description="🎮 O'yinni boshlash"),
        BotCommand(command="ref", description="🔗 Referal link olish"),
        BotCommand(command="top", description="🏆 Guruh reytingi")
    ]

    await bot.set_my_commands(private_commands, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())
    await bot.set_my_commands(private_commands)
    
    # Webhookni o'rnatish
    webhook_info = await bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        await bot.set_webhook(
            url=WEBHOOK_URL,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "inline_query"]
        )
    
    logging.info(f"🚀 Bot Webhook rejimida ishga tushdi: {WEBHOOK_URL}")

async def on_shutdown(bot: Bot):
    """Bot to'xtaganda webhookni o'chirish"""
    logging.info("🛑 Bot to'xtatilmoqda...")
    await bot.delete_webhook()
    await bot.session.close()
    logging.info("✅ Webhook o'chirildi va sessiya yopildi.")

# --- BO'LIM 3: ASOSIY ISHGA TUSHIRISH ---

def main():
    # Bot obyektini yaratish
    bot = Bot(
        token=BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Routerlarni ulash
    dp.include_router(game.router)
    dp.include_router(commands.router)

    # Startup hodisasini ro'yxatdan o'tkazish
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # aiohttp ilovasini yaratish
    app = web.Application()

    # Webhook so'rovlarini qayta ishlovchi (RequestHandler)
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    )

    # Webhook yo'lini ilovaga ulash
    webhook_requests_handler.register(app, path="/webhook")

    # Dispatcher va Botni ilova bilan bog'lash
    setup_application(app, dp, bot=bot)

    # MUHIM: Render uchun dinamik PORT va HOSTni sozlash
    # Render PORTni os.environ orqali beradi
    render_port = int(os.environ.get("PORT", 8080))
    render_host = "0.0.0.0" # Barcha tarmoq interfeyslarini eshitish

    # Serverni ishga tushirish
    web.run_app(app, host=render_host, port=render_port)

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logging.info("🛑 Bot to'xtatildi")
    except Exception as e:
        logging.critical(f"❌ Kutilmagan xato yuz berdi: {e}")