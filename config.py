import os
from dotenv import load_dotenv

load_dotenv()

# --- ASOSIY SOZLAMALAR ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH")
PORT = int(os.getenv("PORT", 8000))

# --- IQTISODIYOT SOZLAMALARI ---
MONEY_RATE = 1000  # $1 moneta = 1,000 so'm
REFERRAL_BONUS = 50000  # Do'st taklif qilganlik uchun o'yin puli (so'mda)

# --- O'YIN REJIMLARI ---
MODES = {
    'classic': {
        'name': '2 kishilik (Classic)',
        'size': 3, 
        'win_len': 3, 
        'players': 2, 
        'symbols': ['❌', '⭕️']
    },
    'battle': {
        'name': '3 kishilik (Battle)',
        'size': 5, 
        'win_len': 4, 
        'players': 3, 
        'symbols': ['❌', '⭕️', '∆']
    }
}

# --- ROBOTLAR SOZLAMALARI ---
ROBOTS = [
    {'id': -1, 'name': 'Merlin'},
    {'id': -2, 'name': 'Smurfetta'},
    {'id': -3, 'name': 'Kung-fu panda'},
    {'id': -4, 'name': 'Morgana'}
]
AI_MOVE_DELAY = 1.2

# --- MUKOFOTLAR JADVALI (O'yin puli - so'mda) ---
REWARDS = {
    'classic': {
        'win': 5000,   
        'draw': 500
    },
    'battle': {
        'rank_1': 10000,
        'rank_2': 5000,
        'draw_full': 1000,   
        'draw_partial': 700 
    }
}

# --- MATCHMAKING ---
MATCHMAKING_WAIT_TIME = 5

# --- DO'KON TIZIMI (CATEGORIZED SKIN SYSTEM) ---
# Turlar: 'simple' (o'yin puli), 'pro' (moneta), 'premium' (moneta + muddatli)
SHOP_SKINS = [
    # 🟢 ODDY SKINLAR (O'yin puliga)
    {'id': 's_olma', 'symbol': '🍎', 'name': 'Olma', 'price': 5000, 'type': 'simple', 'currency': 'cash'},
    {'id': 's_nok', 'symbol': '🍐', 'name': 'Nok', 'price': 15000, 'type': 'simple', 'currency': 'cash'},
    {'id': 's_ananas', 'symbol': '🍍', 'name': 'Ananas', 'price': 50000, 'type': 'simple', 'currency': 'cash'},

    # 🔵 PRO SKINLAR (Moneta $ orqali - Doimiy)
    # $1 = 1000 so'm. Pro skinlar < 10,000 so'm ($10)
    {'id': 'p_uzum', 'symbol': '🍇', 'name': 'Uzum Pro', 'price': 5, 'type': 'pro', 'currency': 'coin'},
    {'id': 'p_olcha', 'symbol': '🍒', 'name': 'Olcha Pro', 'price': 8, 'type': 'pro', 'currency': 'coin'},
    {'id': 'p_limon', 'symbol': '🍋', 'name': 'Limon Pro', 'price': 9, 'type': 'pro', 'currency': 'coin'},

    # 👑 PREMIUM SKINLAR (Moneta $ orqali - 30 Kunlik)
    # Premium skinlar >= 10,000 so'm ($10 - $15)
    {'id': 'pre_brilliant', 'symbol': '💎', 'name': 'Brilliant VIP', 'price': 10, 'type': 'premium', 'currency': 'coin', 'duration': 30},
    {'id': 'pre_yulduz', 'symbol': '🌟', 'name': 'Yulduz VIP', 'price': 12, 'type': 'premium', 'currency': 'coin', 'duration': 30},
    {'id': 'pre_toj', 'symbol': '👑', 'name': 'Qirol VIP', 'price': 15, 'type': 'premium', 'currency': 'coin', 'duration': 30}
]

# --- CHEKLOVLAR ---
MAX_PARALLEL_GAMES = 10 
AFK_TIMEOUT = 45