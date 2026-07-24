ALTER TABLE users
ADD COLUMN IF NOT EXISTS bot_started BOOLEAN NOT NULL DEFAULT FALSE;

-- Migratsiyagacha ro'yxatdan o'tgan real foydalanuvchilarning aksariyati
-- private /start yoki group deep-link orqali kelgan. Telegram baribir botni
-- bloklagan foydalanuvchiga xabar yuborishni rad etadi.
UPDATE users
SET bot_started = TRUE
WHERE is_robot = FALSE;

CREATE INDEX IF NOT EXISTS idx_users_bot_started
ON users(id)
WHERE bot_started = TRUE AND is_robot = FALSE;
