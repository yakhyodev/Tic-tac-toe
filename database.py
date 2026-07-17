"""Async PostgreSQL repository va atomar biznes tranzaksiyalari."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg

from config import REFERRAL_BONUS, REWARDS, ROBOTS, SHOP_SKINS, STARTING_RATING

logger = logging.getLogger(__name__)


class Database:
    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None

    async def connect(self, database_url: str) -> None:
        self.pool = await asyncpg.create_pool(database_url, min_size=1, max_size=10, command_timeout=15)
        logger.info("PostgreSQL pool tayyor")

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
            self.pool = None

    def _pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("Database.connect() hali chaqirilmagan")
        return self.pool

    async def ping(self) -> bool:
        try:
            return await self._pool().fetchval("SELECT 1") == 1
        except (asyncpg.PostgresError, OSError):
            logger.exception("Database readiness tekshiruvi muvaffaqiyatsiz")
            return False

    async def migrate(self) -> None:
        migration_dir = Path(__file__).with_name("migrations")
        await self._pool().execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""
        )
        for path in sorted(migration_dir.glob("*.sql")):
            applied = await self._pool().fetchval("SELECT 1 FROM schema_migrations WHERE version = $1", path.name)
            if applied:
                continue
            sql = path.read_text(encoding="utf-8")
            async with self._pool().acquire() as connection:
                async with connection.transaction():
                    await connection.execute(sql)
                    await connection.execute("INSERT INTO schema_migrations(version) VALUES($1)", path.name)
            logger.info("Migration bajarildi: %s", path.name)

    async def init_static_data(self) -> None:
        async with self._pool().acquire() as connection:
            async with connection.transaction():
                for robot in ROBOTS:
                    await connection.execute(
                        """INSERT INTO users(id, username, full_name, is_robot)
                           VALUES($1, $2, $3, TRUE)
                           ON CONFLICT(id) DO UPDATE SET full_name = EXCLUDED.full_name""",
                        robot["id"],
                        f"bot_{robot['name'].lower().replace(' ', '_')}",
                        robot["name"],
                    )
                    await connection.execute(
                        """INSERT INTO balances(user_id, rating_points)
                           VALUES($1, $2) ON CONFLICT(user_id) DO NOTHING""",
                        robot["id"],
                        STARTING_RATING,
                    )

    async def register_user(
        self,
        user_id: int,
        username: str | None,
        full_name: str,
        referred_by: int | None = None,
    ) -> bool:
        async with self._pool().acquire() as connection:
            async with connection.transaction():
                valid_inviter = None
                if referred_by and referred_by != user_id:
                    valid_inviter = await connection.fetchval(
                        "SELECT id FROM users WHERE id = $1 AND is_robot = FALSE", referred_by
                    )
                inserted = await connection.fetchval(
                    """INSERT INTO users(id, username, full_name, referred_by)
                       VALUES($1, $2, $3, $4)
                       ON CONFLICT(id) DO NOTHING
                       RETURNING id""",
                    user_id,
                    username,
                    full_name,
                    valid_inviter,
                )
                if inserted:
                    await connection.execute(
                        """INSERT INTO balances(user_id, rating_points)
                           VALUES($1, $2) ON CONFLICT(user_id) DO NOTHING""",
                        user_id,
                        STARTING_RATING,
                    )
                    if valid_inviter:
                        await connection.execute(
                            """INSERT INTO referrals(inviter_id, referred_id, reward)
                               VALUES($1, $2, $3) ON CONFLICT(referred_id) DO NOTHING""",
                            valid_inviter,
                            user_id,
                            REFERRAL_BONUS,
                        )
                    return True

                await connection.execute(
                    "UPDATE users SET username = $1, full_name = $2 WHERE id = $3",
                    username,
                    full_name,
                    user_id,
                )
                return False

    async def ensure_user_exists(self, user_id: int, full_name: str, username: str | None = None) -> bool:
        return await self.register_user(user_id, username, full_name)

    async def get_user_profile(self, user_id: int) -> dict[str, Any] | None:
        row = await self._pool().fetchrow(
            """SELECT u.full_name, b.balance, b.coins, b.active_skin, b.rating_points,
                      COUNT(gr.id) FILTER (WHERE gr.rank = 1 AND gr.is_draw = FALSE) AS wins,
                      COUNT(gr.id) FILTER (WHERE gr.rank > 1 AND gr.is_draw = FALSE) AS losses,
                      COUNT(gr.id) FILTER (WHERE gr.is_draw = TRUE) AS draws
               FROM users u
               JOIN balances b ON b.user_id = u.id
               LEFT JOIN game_results gr ON gr.user_id = u.id
               WHERE u.id = $1
               GROUP BY u.id, u.full_name, b.balance, b.coins, b.active_skin, b.rating_points""",
            user_id,
        )
        return dict(row) if row else None

    async def get_referrals_paged(
        self, user_id: int, page: int = 1, page_size: int = 10
    ) -> tuple[list[dict[str, Any]], int]:
        offset = max(page - 1, 0) * page_size
        rows = await self._pool().fetch(
            """SELECT u.full_name, r.created_at, r.status
               FROM referrals r JOIN users u ON u.id = r.referred_id
               WHERE r.inviter_id = $1 ORDER BY r.created_at DESC LIMIT $2 OFFSET $3""",
            user_id,
            page_size,
            offset,
        )
        total = await self._pool().fetchval("SELECT COUNT(*) FROM referrals WHERE inviter_id = $1", user_id)
        return [dict(row) for row in rows], int(total or 0)

    @staticmethod
    def _reward(mode: str, rank: int, is_draw: bool, draw_type: str | None) -> int:
        if mode == "classic":
            return REWARDS["classic"]["draw" if is_draw else "win"] if is_draw or rank == 1 else 0
        if is_draw:
            key = "draw_partial" if draw_type == "partial" else "draw_full"
            return REWARDS["battle"][key]
        if rank == 1:
            return REWARDS["battle"]["rank_1"]
        if rank == 2:
            return REWARDS["battle"]["rank_2"]
        return 0

    @staticmethod
    def _rating_delta(mode: str, rank: int, is_draw: bool) -> int:
        if is_draw:
            return 5
        if mode == "classic":
            return 25 if rank == 1 else -10
        return {1: 30, 2: 10, 3: -10}.get(rank, -10)

    async def process_game_results(
        self, game_id: str, mode: str, participants: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        results: list[dict[str, Any]] = []
        referral_notifications: list[dict[str, Any]] = []
        async with self._pool().acquire() as connection:
            async with connection.transaction():
                for participant in participants:
                    user_id = int(participant["user_id"])
                    rank = int(participant["rank"])
                    is_draw = bool(participant.get("is_draw", False))
                    draw_type = participant.get("draw_type")
                    reward = self._reward(mode, rank, is_draw, draw_type)
                    inserted = await connection.fetchrow(
                        """INSERT INTO game_results(game_id, user_id, mode, rank, is_draw, draw_type, reward)
                           VALUES($1, $2, $3, $4, $5, $6, $7)
                           ON CONFLICT(game_id, user_id) DO NOTHING
                           RETURNING reward, rank, is_draw, draw_type""",
                        game_id,
                        user_id,
                        mode,
                        rank,
                        is_draw,
                        draw_type,
                        reward,
                    )
                    if not inserted:
                        existing = await connection.fetchrow(
                            """SELECT reward, rank, is_draw, draw_type FROM game_results
                               WHERE game_id = $1 AND user_id = $2""",
                            game_id,
                            user_id,
                        )
                        reward = int(existing["reward"]) if existing else 0
                        results.append(
                            {
                                "user_id": user_id,
                                "reward": reward,
                                "rank": rank,
                                "is_draw": is_draw,
                                "draw_type": draw_type,
                            }
                        )
                        continue

                    if user_id > 0:
                        rating_delta = self._rating_delta(mode, rank, is_draw)
                        await connection.execute(
                            """UPDATE balances
                               SET balance = balance + $1,
                                   rating_points = GREATEST(0, rating_points + $2)
                               WHERE user_id = $3""",
                            reward,
                            rating_delta,
                            user_id,
                        )
                        await connection.execute(
                            """INSERT INTO wallet_transactions
                               (user_id, currency, amount, transaction_type, reference_id, idempotency_key)
                               VALUES($1, 'cash', $2, 'game_reward', $3, $4)
                               ON CONFLICT(idempotency_key) DO NOTHING""",
                            user_id,
                            reward,
                            game_id,
                            f"game:{game_id}:{user_id}",
                        )
                        referral = await connection.fetchrow(
                            """UPDATE referrals SET status = 'rewarded', rewarded_at = NOW()
                               WHERE referred_id = $1 AND status = 'pending'
                               RETURNING inviter_id, reward""",
                            user_id,
                        )
                        if referral:
                            inviter_id = int(referral["inviter_id"])
                            referral_reward = int(referral["reward"])
                            await connection.execute(
                                "UPDATE balances SET balance = balance + $1 WHERE user_id = $2",
                                referral_reward,
                                inviter_id,
                            )
                            await connection.execute(
                                """INSERT INTO wallet_transactions
                                   (user_id, currency, amount, transaction_type, reference_id, idempotency_key)
                                   VALUES($1, 'cash', $2, 'referral_reward', $3, $4)
                                   ON CONFLICT(idempotency_key) DO NOTHING""",
                                inviter_id,
                                referral_reward,
                                str(user_id),
                                f"referral:{user_id}",
                            )
                            referral_notifications.append(
                                {"inviter_id": inviter_id, "reward": referral_reward, "referred_id": user_id}
                            )
                    results.append(
                        {"user_id": user_id, "reward": reward, "rank": rank, "is_draw": is_draw, "draw_type": draw_type}
                    )
        return {"results": results, "referrals": referral_notifications}

    async def check_and_clean_expired_skins(self, user_id: int) -> None:
        async with self._pool().acquire() as connection:
            async with connection.transaction():
                expired = await connection.fetch(
                    """DELETE FROM inventory
                       WHERE user_id = $1 AND expires_at IS NOT NULL AND expires_at <= NOW()
                       RETURNING skin_id""",
                    user_id,
                )
                if expired:
                    expired_ids = [row["skin_id"] for row in expired]
                    await connection.execute(
                        """UPDATE balances SET active_skin = 'default'
                           WHERE user_id = $1 AND active_skin = ANY($2::text[])""",
                        user_id,
                        expired_ids,
                    )

    async def get_user_inventory(self, user_id: int) -> list[str]:
        await self.check_and_clean_expired_skins(user_id)
        rows = await self._pool().fetch("SELECT skin_id FROM inventory WHERE user_id = $1 ORDER BY bought_at", user_id)
        return [row["skin_id"] for row in rows]

    async def get_user_inventory_with_time(self, user_id: int) -> list[dict[str, Any]]:
        await self.check_and_clean_expired_skins(user_id)
        rows = await self._pool().fetch(
            "SELECT skin_id, expires_at FROM inventory WHERE user_id = $1 ORDER BY bought_at", user_id
        )
        return [dict(row) for row in rows]

    async def buy_skin(self, user_id: int, skin_id: str) -> dict[str, Any]:
        skin = next((item for item in SHOP_SKINS if item["id"] == skin_id), None)
        if not skin:
            return {"success": False, "msg": "Skin topilmadi."}
        await self.check_and_clean_expired_skins(user_id)
        async with self._pool().acquire() as connection:
            async with connection.transaction():
                profile = await connection.fetchrow(
                    "SELECT balance, coins FROM balances WHERE user_id = $1 FOR UPDATE", user_id
                )
                if not profile:
                    return {"success": False, "msg": "Avval /start buyrug'ini bosing."}
                owned = await connection.fetchval(
                    "SELECT 1 FROM inventory WHERE user_id = $1 AND skin_id = $2", user_id, skin_id
                )
                if owned:
                    return {"success": False, "msg": "Bu skin inventaringizda mavjud."}

                currency = skin["currency"]
                column = "coins" if currency == "coin" else "balance"
                if int(profile[column]) < int(skin["price"]):
                    unit = "moneta" if currency == "coin" else "o'yin puli"
                    return {"success": False, "msg": f"{unit.capitalize()} yetarli emas."}

                await connection.execute(
                    f"UPDATE balances SET {column} = {column} - $1 WHERE user_id = $2",
                    int(skin["price"]),
                    user_id,
                )
                expires_at = None
                if skin["type"] == "premium":
                    expires_at = datetime.now(UTC) + timedelta(days=int(skin.get("duration", 30)))
                await connection.execute(
                    """INSERT INTO inventory(user_id, skin_id, expires_at)
                       VALUES($1, $2, $3)""",
                    user_id,
                    skin_id,
                    expires_at,
                )
                await connection.execute(
                    """INSERT INTO wallet_transactions
                       (user_id, currency, amount, transaction_type, reference_id, idempotency_key)
                       VALUES($1, $2, $3, 'skin_purchase', $4, $5)""",
                    user_id,
                    currency,
                    -int(skin["price"]),
                    skin_id,
                    f"skin:{user_id}:{skin_id}:{uuid.uuid4()}",
                )
        return {"success": True, "msg": f"{skin['symbol']} {skin['name']} sotib olindi."}

    async def exchange_cash_for_coins(self, user_id: int, coins: int, rate: int) -> dict[str, Any]:
        if coins <= 0:
            return {"success": False, "msg": "Noto'g'ri miqdor."}
        cash = coins * rate
        reference = f"exchange:{user_id}:{datetime.now(UTC).isoformat()}"
        async with self._pool().acquire() as connection:
            async with connection.transaction():
                balance = await connection.fetchval(
                    "SELECT balance FROM balances WHERE user_id = $1 FOR UPDATE", user_id
                )
                if balance is None:
                    return {"success": False, "msg": "Avval /start buyrug'ini bosing."}
                if int(balance) < cash:
                    return {"success": False, "msg": "O'yin puli yetarli emas."}
                await connection.execute(
                    "UPDATE balances SET balance = balance - $1, coins = coins + $2 WHERE user_id = $3",
                    cash,
                    coins,
                    user_id,
                )
                await connection.executemany(
                    """INSERT INTO wallet_transactions
                       (user_id, currency, amount, transaction_type, reference_id, idempotency_key)
                       VALUES($1, $2, $3, 'exchange', $4, $5)""",
                    [
                        (user_id, "cash", -cash, reference, f"{reference}:cash"),
                        (user_id, "coin", coins, reference, f"{reference}:coin"),
                    ],
                )
        return {"success": True, "msg": f"{cash:,} so'm → {coins} moneta almashtirildi."}

    async def set_active_skin(self, user_id: int, skin_id: str) -> bool:
        await self.check_and_clean_expired_skins(user_id)
        if skin_id != "default":
            owned = await self._pool().fetchval(
                "SELECT 1 FROM inventory WHERE user_id = $1 AND skin_id = $2", user_id, skin_id
            )
            if not owned:
                return False
        result = await self._pool().execute("UPDATE balances SET active_skin = $1 WHERE user_id = $2", skin_id, user_id)
        return result.endswith("1")

    async def get_global_top(self, limit: int = 35) -> list[dict[str, Any]]:
        rows = await self._pool().fetch(
            """SELECT u.full_name, b.rating_points, b.balance, b.coins
               FROM users u JOIN balances b ON b.user_id = u.id
               WHERE u.is_robot = FALSE
               ORDER BY b.rating_points DESC, b.balance DESC LIMIT $1""",
            limit,
        )
        return [dict(row) for row in rows]

    async def save_game(self, game_id: str, status: str, payload: dict[str, Any]) -> None:
        await self._pool().execute(
            """INSERT INTO game_sessions(game_id, status, payload, updated_at)
               VALUES($1, $2, $3::jsonb, NOW())
               ON CONFLICT(game_id) DO UPDATE
               SET status = EXCLUDED.status, payload = EXCLUDED.payload, updated_at = NOW()""",
            game_id,
            status,
            json.dumps(payload, ensure_ascii=False),
        )

    async def load_open_games(self) -> dict[str, dict[str, Any]]:
        rows = await self._pool().fetch(
            "SELECT game_id, payload FROM game_sessions WHERE status IN ('waiting', 'active')"
        )
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            payload = row["payload"]
            result[row["game_id"]] = json.loads(payload) if isinstance(payload, str) else dict(payload)
        return result

    async def delete_game(self, game_id: str) -> None:
        await self._pool().execute(
            "UPDATE game_sessions SET status = 'finished', updated_at = NOW() WHERE game_id = $1",
            game_id,
        )


db = Database()
