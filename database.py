import psycopg2
from psycopg2 import pool, InterfaceError, OperationalError
from psycopg2.extras import RealDictCursor
import logging
from datetime import datetime, timedelta
from config import DATABASE_URL, REWARDS, ROBOTS, SHOP_SKINS

# --- BO'LIM 1: MA'LUMOTLAR BAZASI STRUKTURASI ---

class Database:
    def __init__(self):
        try:
            self.connection_pool = pool.SimpleConnectionPool(
                1, 20, DATABASE_URL, sslmode='require'
            )
            print("✅ Database Pool yaratildi!")
            self.create_tables()
            self.init_static_data()
        except Exception as e:
            logging.error(f"❌ Baza bilan ulanishda xato: {e}")

    def get_conn(self):
        return self.connection_pool.getconn()

    def put_conn(self, conn):
        self.connection_pool.putconn(conn)

    def _execute_query(self, query, params=None, fetch=False, commit=True):
        conn = self.get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                try:
                    cur.execute(query, params)
                    if commit:
                        conn.commit()
                    return cur.fetchall() if fetch else True
                except (InterfaceError, OperationalError):
                    logging.info("🔄 Baza ulanishi yangilanmoqda...")
                    self.put_conn(conn)
                    conn = self.get_conn()
                    with conn.cursor(cursor_factory=RealDictCursor) as cur_retry:
                        cur_retry.execute(query, params)
                        if commit:
                            conn.commit()
                        return cur_retry.fetchall() if fetch else True
        except Exception as e:
            logging.error(f"❌ SQL Xatolik: {e} | Query: {query}")
            return None
        finally:
            self.put_conn(conn)

    def create_tables(self):
        # 1. Asosiy jadvallar
        queries = [
            """CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                referred_by BIGINT,
                is_robot BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );""",
            """CREATE TABLE IF NOT EXISTS balances (
                user_id BIGINT PRIMARY KEY REFERENCES users(id),
                balance BIGINT DEFAULT 0,
                coins BIGINT DEFAULT 0,
                active_skin TEXT DEFAULT 'default'
            );""",
            """CREATE TABLE IF NOT EXISTS inventory (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(id),
                skin_id TEXT,
                bought_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NULL,
                UNIQUE(user_id, skin_id)
            );""",
            """CREATE TABLE IF NOT EXISTS game_results (
                id SERIAL PRIMARY KEY,
                game_id TEXT,
                user_id BIGINT REFERENCES users(id),
                rank INT,
                is_draw BOOLEAN DEFAULT FALSE,
                reward BIGINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );"""
        ]
        for q in queries:
            self._execute_query(q)

        # 2. XAVFSIZ MIGRATSIYA
        migrations = [
            "ALTER TABLE balances ADD COLUMN IF NOT EXISTS coins BIGINT DEFAULT 0;",
            "ALTER TABLE inventory ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP NULL;"
        ]
        for m in migrations:
            self._execute_query(m)
            
        print("✅ Jadvallar va migratsiyalar tekshirildi.")

    def init_static_data(self):
        for robot in ROBOTS:
            self._execute_query(
                "INSERT INTO users (id, username, full_name, is_robot) VALUES (%s, %s, %s, TRUE) ON CONFLICT (id) DO NOTHING",
                (robot['id'], f"bot_{robot['name'].lower()}", robot['name'])
            )
            self._execute_query("INSERT INTO balances (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (robot['id'],))

# --- BO'LIM 2: FOYDALANUVCHI VA REFERALLAR ---

    def register_user(self, user_id, username, full_name, referred_by=None):
        """Lichkada /start bosilganda to'liq ro'yxatdan o'tkazish"""
        check = self._execute_query("SELECT 1 FROM users WHERE id = %s", (user_id,), fetch=True)
        if not check:
            self._execute_query(
                "INSERT INTO users (id, username, full_name, referred_by) VALUES (%s, %s, %s, %s)",
                (user_id, username, full_name, referred_by)
            )
            # MUHIM: Yangi foydalanuvchiga default skin berish
            self._execute_query(
                "INSERT INTO balances (user_id, balance, coins, active_skin) VALUES (%s, 0, 0, 'default')", 
                (user_id,)
            )
            return True
        # Mavjud foydalanuvchi ma'lumotlarini yangilash
        self._execute_query("UPDATE users SET full_name = %s, username = %s WHERE id = %s", (full_name, username, user_id))
        return False

    def ensure_user_exists(self, user_id, full_name, username=None):
        """Guruhda o'yinga qo'shilganda start bosmagan bo'lsa ham bazaga qo'shish"""
        check = self._execute_query("SELECT 1 FROM users WHERE id = %s", (user_id,), fetch=True)
        if not check:
            # Foydalanuvchi bazada yo'q bo'lsa, uni yaratamiz
            self._execute_query(
                "INSERT INTO users (id, username, full_name) VALUES (%s, %s, %s)",
                (user_id, username, full_name)
            )
            # MUHIM: Bu yerda ham default skin berishni ta'minlaymiz
            self._execute_query(
                "INSERT INTO balances (user_id, balance, coins, active_skin) VALUES (%s, 0, 0, 'default')", 
                (user_id,)
            )
            return True
        return False

    def get_users_count(self):
        """Jami real foydalanuvchilar sonini olish"""
        res = self._execute_query("SELECT COUNT(*) FROM users WHERE is_robot = FALSE", fetch=True)
        return res[0]['count'] if res else 0

    def get_user_profile(self, user_id):
        query = """
            SELECT u.full_name, b.balance, b.coins, b.active_skin,
            (SELECT COUNT(*) FROM game_results WHERE user_id = u.id AND rank = 1) as wins
            FROM users u JOIN balances b ON u.id = b.user_id WHERE u.id = %s
        """
        res = self._execute_query(query, (user_id,), fetch=True)
        return res[0] if res else None

    def get_referrals_paged(self, user_id, page=1, page_size=10):
        offset = (page - 1) * page_size
        query = "SELECT full_name, created_at FROM users WHERE referred_by = %s ORDER BY created_at DESC LIMIT %s OFFSET %s"
        count_query = "SELECT COUNT(*) FROM users WHERE referred_by = %s"
        
        refs = self._execute_query(query, (user_id, page_size, offset), fetch=True)
        total_res = self._execute_query(count_query, (user_id,), fetch=True)
        total = total_res[0]['count'] if total_res else 0
        return refs, total

# --- BO'LIM 3: O'YIN NATIJALARI ---

    def process_game_results(self, game_id, participants_ranks):
        results_summary = []
        total_players = len(participants_ranks)
        for p in participants_ranks:
            uid, rank, is_draw = p['user_id'], p['rank'], p['is_draw']
            reward = self._calculate_reward(total_players, rank, is_draw, participants_ranks)
            self._execute_query(
                "INSERT INTO game_results (game_id, user_id, rank, is_draw, reward) VALUES (%s, %s, %s, %s, %s)",
                (game_id, uid, rank, is_draw, reward)
            )
            if uid > 0:
                self._execute_query("UPDATE balances SET balance = balance + %s WHERE user_id = %s", (reward, uid))
            results_summary.append({'user_id': uid, 'reward': reward, 'rank': rank, 'is_draw': is_draw})
        return results_summary

    def _calculate_reward(self, total_players, rank, is_draw, all_players):
        if total_players == 2:
            if is_draw:
                return REWARDS['classic']['draw']
            if rank == 1:
                return REWARDS['classic']['win']
            return 0
        elif total_players == 3:
            if is_draw:
                winners_count = len([p for p in all_players if p['rank'] != 99 and not p['is_draw']])
                if winners_count == 0:
                    return REWARDS['battle']['draw_full']
                return REWARDS['battle']['draw_partial']
            if rank == 1:
                return REWARDS['battle']['rank_1']
            if rank == 2:
                return REWARDS['battle']['rank_2']
        return 0

# --- BO'LIM 4: DO'KON VA INVENTAR ---

    def buy_skin(self, user_id, skin_id):
        self.check_and_clean_expired_skins(user_id)
        check_query = "SELECT 1 FROM inventory WHERE user_id = %s AND skin_id = %s"
        owned = self._execute_query(check_query, (user_id, skin_id), fetch=True)
        if owned:
            return {"success": False, "msg": "Sizda bu meva allaqachon mavjud! ✅"}

        skin = next((s for s in SHOP_SKINS if s['id'] == skin_id), None)
        if not skin:
            return {"success": False, "msg": "Skin topilmadi!"}

        profile = self.get_user_profile(user_id)
        if not profile:
            return {"success": False, "msg": "Profil topilmadi!"}

        if skin['currency'] == 'coin':
            if profile['coins'] < skin['price']:
                return {"success": False, "msg": "Monetalar ($) yetarli emas! ❌"}
            self._execute_query("UPDATE balances SET coins = coins - %s WHERE user_id = %s", (skin['price'], user_id))
        else:
            if profile['balance'] < skin['price']:
                return {"success": False, "msg": "O'yin puli yetarli emas! ❌"}
            self._execute_query("UPDATE balances SET balance = balance - %s WHERE user_id = %s", (skin['price'], user_id))

        expiry_date = None
        if skin.get('type') == 'premium':
            expiry_date = datetime.now() + timedelta(days=skin.get('duration', 30))

        self._execute_query(
            "INSERT INTO inventory (user_id, skin_id, expires_at) VALUES (%s, %s, %s)",
            (user_id, skin_id, expiry_date)
        )
        return {"success": True, "msg": f"{skin['symbol']} {skin['name']} muvaffaqiyatli sotib olindi!"}

    def check_and_clean_expired_skins(self, user_id):
        now = datetime.now()
        expired = self._execute_query(
            "SELECT skin_id FROM inventory WHERE user_id = %s AND expires_at IS NOT NULL AND expires_at < %s",
            (user_id, now), fetch=True
        )
        if expired:
            for item in expired:
                self._execute_query("DELETE FROM inventory WHERE user_id = %s AND skin_id = %s", (user_id, item['skin_id']))
                self._execute_query(
                    "UPDATE balances SET active_skin = 'default' WHERE user_id = %s AND active_skin = %s",
                    (user_id, item['skin_id'])
                )

    def get_user_inventory(self, user_id):
        self.check_and_clean_expired_skins(user_id)
        res = self._execute_query("SELECT skin_id FROM inventory WHERE user_id = %s", (user_id,), fetch=True)
        return [row['skin_id'] for row in res] if res else []

    def get_user_inventory_with_time(self, user_id):
        self.check_and_clean_expired_skins(user_id)
        query = "SELECT skin_id, expires_at FROM inventory WHERE user_id = %s"
        return self._execute_query(query, (user_id,), fetch=True)

    def set_active_skin(self, user_id, skin_id):
        check = self._execute_query("SELECT 1 FROM inventory WHERE user_id = %s AND skin_id = %s", (user_id, skin_id), fetch=True)
        if check or skin_id == 'default':
            self._execute_query("UPDATE balances SET active_skin = %s WHERE user_id = %s", (skin_id, user_id))
            return True
        return False

# --- BO'LIM 5: REYTING ---

    def get_global_top(self, limit=35):
        query = """
            SELECT u.full_name, b.balance, b.coins FROM users u 
            JOIN balances b ON u.id = b.user_id 
            WHERE u.is_robot = FALSE ORDER BY b.balance DESC LIMIT %s
        """
        return self._execute_query(query, (limit,), fetch=True)

db = Database()