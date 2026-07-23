-- Eski monetalarni foydalanuvchi yo'qotmasligi uchun avval o'yin puliga qaytaramiz.
-- Avvalgi almashtirish kursi: 1 moneta = 1 000 so'm.
UPDATE balances
SET balance = balance + (coins * 1000)
WHERE coins > 0;

ALTER TABLE balances DROP COLUMN IF EXISTS coins;
