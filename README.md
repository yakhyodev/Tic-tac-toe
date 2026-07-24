# UzbekToe Telegram Bot

Aiogram 3, aiohttp va PostgreSQL asosidagi Classic/Battle Tic-Tac-Toe bot.

## Imkoniyatlar

- 2 kishilik 3×3 Classic va 3 kishilik 5×5 Battle
- Shaxsiy matchmaking, guruh o'yinlari va robotlar
- Bot a'zo bo'lmagan chatlarda `@bot_username` orqali inline Classic/Battle o'yinlari
- Guruh o'yiniga private-chat deep-link orqali xavfsiz qo'shilish va aynan o'yin xabariga qaytish
- 45 soniyalik taymaut, `/cancel` va kutilayotgan o'yin TTL'i
- Restartdan keyin ochiq o'yinlarni PostgreSQL'dan tiklash
- Reyting, referral, yagona o'yin puli, atomar shop va premium skin muddati
- Telegram webhook secret tekshiruvi
- Railway health/readiness endpointlari

## Lokal ishga tushirish

Python 3.12 talab qilinadi.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

`.env` qiymatlarini to'ldiring va PostgreSQL ishga tushganidan keyin:

```powershell
.\.venv\Scripts\python migrate.py
.\.venv\Scripts\python bot.py
```

Tekshiruv:

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\ruff check .
.\.venv\Scripts\pip-audit -r requirements.txt
```

## Railway deploy

1. GitHub repositoryni Railway projectga ulang.
2. Projectga PostgreSQL service qo'shing.
3. Bot service uchun public domain yarating.
4. Quyidagi variables'ni kiriting:

```text
BOT_TOKEN=<BotFather token>
DATABASE_URL=${{Postgres.DATABASE_URL}}
WEBHOOK_BASE_URL=https://${{RAILWAY_PUBLIC_DOMAIN}}
WEBHOOK_PATH=/webhook
WEBHOOK_SECRET=<uzun random secret>
ENVIRONMENT=production
LOG_LEVEL=INFO
```

`PORT` Railway tomonidan avtomatik beriladi. `railway.toml` Docker build, migration, start command, bitta replica, healthcheck va restart policy'ni boshqaradi.

`002_remove_coins.sql` eski monetalarni 1:1 000 kursda o'yin puliga qaytarib, moneta ustunini olib tashlaydi. Barcha
skinlar faqat o'yinda ishlab topilgan balansdan xarid qilinadi.

Deploydan keyin tekshiring:

- `https://<domain>/health` → HTTP 200
- `https://<domain>/ready` → HTTP 200
- Railway logida migration va webhook xatosi yo'q
- Telegram'da `/start`, `/game`, `/shop`, `/top`

### BotFather inline-mode checklist

1. `@BotFather` → `/setinline` → botni tanlang → masalan, `Classic yoki Battle o'yinini tanlang` placeholderini kiriting.
2. `@BotFather` → `/setinlinefeedback` → botni tanlang → `100%` ni yoqing. Bu `ChosenInlineResult` va `inline_message_id` kelishi uchun shart.
3. Servisni qayta deploy qiling; webhook `inline_query` va `chosen_inline_result` update turlarini ham qabul qiladi.
4. Bot a'zo bo'lmagan test chatda `@bot_username` yozing, rejimni yuboring, boshqa akkaunt bilan qo'shiling va yurishdan keyin aynan shu inline xabar yangilanishini tekshiring.

## Xavfsizlik

`.env` Git'ga kiritilmaydi. Ushbu repository tarixida oldin real `.env` bo'lgan bo'lsa, production deploydan avval BotFather tokeni va database credentiallarini almashtiring.

Production webhook `WEBHOOK_SECRET` bo'lmasa ishga tushmaydi. Shutdown webhookni o'chirmaydi, shuning uchun redeploy vaqtida update'lar yo'qolmaydi.
