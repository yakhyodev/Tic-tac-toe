"""Ilova va mahsulot konfiguratsiyasi."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _environment() -> str:
    if os.getenv("ENVIRONMENT"):
        return os.environ["ENVIRONMENT"].lower()
    return "production" if os.getenv("RAILWAY_ENVIRONMENT") else "development"


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    webhook_base_url: str
    webhook_path: str
    webhook_secret: str
    host: str
    port: int
    environment: str
    log_level: str

    @property
    def webhook_url(self) -> str:
        legacy_url = os.getenv("WEBHOOK_URL", "").strip()
        if legacy_url:
            legacy_url = legacy_url.rstrip("/")
            return legacy_url if legacy_url.endswith(self.webhook_path) else f"{legacy_url}{self.webhook_path}"
        return f"{self.webhook_base_url.rstrip('/')}{self.webhook_path}"

    @classmethod
    def from_env(cls) -> Settings:
        environment = _environment()
        base_url = os.getenv("WEBHOOK_BASE_URL", "").strip()
        legacy_url = os.getenv("WEBHOOK_URL", "").strip()
        if not base_url and legacy_url:
            path = os.getenv("WEBHOOK_PATH", "/webhook")
            base_url = legacy_url[: -len(path)] if legacy_url.endswith(path) else legacy_url

        values = {
            "BOT_TOKEN": os.getenv("BOT_TOKEN", "").strip(),
            "DATABASE_URL": os.getenv("DATABASE_URL", "").strip(),
            "WEBHOOK_BASE_URL": base_url,
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise RuntimeError(f"Majburiy environment o'zgaruvchilar yo'q: {', '.join(missing)}")

        webhook_secret = os.getenv("WEBHOOK_SECRET", "").strip()
        if environment == "production" and not webhook_secret:
            raise RuntimeError("Production uchun WEBHOOK_SECRET majburiy")
        if webhook_secret and (
            not 1 <= len(webhook_secret) <= 256 or re.fullmatch(r"[A-Za-z0-9_-]+", webhook_secret) is None
        ):
            raise RuntimeError("WEBHOOK_SECRET faqat A-Z, a-z, 0-9, _ va - belgilaridan iborat bo'lishi kerak")
        if environment == "production" and not base_url.startswith("https://"):
            raise RuntimeError("Production WEBHOOK_BASE_URL HTTPS bo'lishi kerak")

        path = os.getenv("WEBHOOK_PATH", "/webhook").strip()
        if not path.startswith("/"):
            path = f"/{path}"

        return cls(
            bot_token=values["BOT_TOKEN"],
            database_url=values["DATABASE_URL"],
            webhook_base_url=base_url,
            webhook_path=path,
            webhook_secret=webhook_secret or "local-development-secret",
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8080")),
            environment=environment,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )


# Iqtisodiyot
REFERRAL_BONUS = 50_000
STARTING_RATING = 1_000

MODES = {
    "classic": {"name": "2 kishilik (Classic)", "size": 3, "win_len": 3, "players": 2},
    "battle": {"name": "3 kishilik (Battle)", "size": 5, "win_len": 4, "players": 3},
}

DEFAULT_VISUALS = ["❌", "⭕️", "△"]
FALLBACK_VISUALS = ["💎", "🌟", "🔥", "🍀", "🌀"]

ROBOTS = [
    {"id": -1, "name": "Merlin"},
    {"id": -2, "name": "Smurfetta"},
    {"id": -3, "name": "Kung-fu panda"},
    {"id": -4, "name": "Morgana"},
]

AI_MOVE_DELAY = 1.2
MATCHMAKING_WAIT_TIME = 5
PREP_GAME_TTL = 300
AFK_TIMEOUT = 45
MAX_PARALLEL_GAMES = 10

REWARDS = {
    "classic": {"win": 5_000, "draw": 500},
    "battle": {"rank_1": 10_000, "rank_2": 5_000, "draw_full": 1_000, "draw_partial": 700},
}

SHOP_SKINS = [
    {"id": "s_olma", "symbol": "🍎", "name": "Olma", "price": 25_000, "type": "simple"},
    {"id": "s_nok", "symbol": "🍐", "name": "Nok", "price": 75_000, "type": "simple"},
    {"id": "s_ananas", "symbol": "🍍", "name": "Ananas", "price": 150_000, "type": "simple"},
    {"id": "p_uzum", "symbol": "🍇", "name": "Uzum Pro", "price": 250_000, "type": "pro"},
    {"id": "p_olcha", "symbol": "🍒", "name": "Olcha Pro", "price": 400_000, "type": "pro"},
    {"id": "p_limon", "symbol": "🍋", "name": "Limon Pro", "price": 600_000, "type": "pro"},
    {
        "id": "pre_brilliant",
        "symbol": "💎",
        "name": "Brilliant VIP",
        "price": 900_000,
        "type": "premium",
        "duration": 30,
    },
    {
        "id": "pre_yulduz",
        "symbol": "🌟",
        "name": "Yulduz VIP",
        "price": 1_200_000,
        "type": "premium",
        "duration": 30,
    },
    {
        "id": "pre_toj",
        "symbol": "👑",
        "name": "Qirol VIP",
        "price": 1_500_000,
        "type": "premium",
        "duration": 30,
    },
]
