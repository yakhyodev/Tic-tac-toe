import logging
from datetime import datetime
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.exceptions import TelegramBadRequest

# Loyiha modullari
from database import db
from config import SHOP_SKINS, REFERRAL_BONUS, MONEY_RATE

router = Router()

# --- YORDAMCHI FUNKSIYALAR ---

def get_main_keyboard():
    """Bot lichkasi uchun asosiy tugmalar menyusi"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎮 O'yinni boshlash")],
            [KeyboardButton(text="👤 Profilim"), KeyboardButton(text="🎨 Skinlarim")],
            [KeyboardButton(text="🛍 Do'kon"), KeyboardButton(text="🤝 Referallar")],
            [KeyboardButton(text="🌍 Global Reyting")]
        ],
        resize_keyboard=True
    )

def get_pm_keyboard(bot_username: str):
    """Lichkaga o'tish tugmasi (Guruhlar uchun)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Botga o'tish (Lichka)", url=f"https://t.me/{bot_username}")]
    ])

# --- BO'LIM 1: START VA ASOSIY MENYU ---

@router.message(CommandStart())
async def cmd_start(message: types.Message, bot: Bot):
    """Foydalanuvchini ro'yxatdan o'tkazish va menyuni ko'rsatish"""
    user = message.from_user
    args = message.text.split()
    referred_by = None
    
    if len(args) > 1 and args[1].isdigit():
        inviter_id = int(args[1])
        if inviter_id != user.id:
            referred_by = inviter_id

    # register_user yangi bo'lsa True qaytaradi
    is_new = db.register_user(user.id, user.username, user.full_name, referred_by)
    
    if is_new and referred_by:
        try:
            # Taklif qiluvchi balansiga bonus qo'shish
            db._execute_query(
                "UPDATE balances SET balance = balance + %s WHERE user_id = %s", 
                (REFERRAL_BONUS, referred_by)
            )
            # Taklif qiluvchiga xabar yuborish
            await bot.send_message(
                referred_by, 
                f"💰 **Ajoyib yangilik!**\n\nSiz taklif qilgan do'stingiz {user.full_name} qo'shildi! "
                f"Hisobingizga **{REFERRAL_BONUS:,} so'm** bonus o'tkazildi. ✅"
            )
        except Exception as e:
            logging.error(f"Referal bonus xatosi: {e}")

    bot_info = await bot.get_me() 

    if message.chat.type != "private":
        return await message.answer(
            f"👋 Salom, {user.full_name}! Bot lichkasida matchmaking va do'kon mavjud.", 
            reply_markup=get_pm_keyboard(bot_info.username)
        )

    welcome_text = (
        f"👋 Salom, {user.full_name}!\n\n"
        "🎮 **Tic-Tac-Toe Matchmaking Botiga** xush kelibsiz.\n\n"
        f"🤝 Do'stlarni taklif qiling va har biri uchun **{REFERRAL_BONUS:,} so'm** oling!\n\n"
        "Quyidagi menyu orqali botdan foydalanishingiz mumkin 👇"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

# --- BO'LIM 2: REFERAL VA PAGINATION ---

@router.message(F.text == "🤝 Referallar")
@router.message(Command("ref"))
async def cmd_ref(message: types.Message, bot: Bot):
    """Referal link va taklif qilinganlar ro'yxati"""
    user_id = message.from_user.id
    bot_info = await bot.get_me()
    
    if message.chat.type != "private":
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        try:
            await bot.send_message(user_id, f"🔗 Sizning referal havolangiz:\n`{ref_link}`", parse_mode="Markdown")
            return await message.reply(f"📥 {message.from_user.first_name}, havolani lichkangizga yubordim! ✅")
        except Exception:
            return await message.reply("⚠️ Avval botga lichkada /start buyrug'ini yuboring!", reply_markup=get_pm_keyboard(bot_info.username))

    await show_referrals(message, bot, page=1)

async def show_referrals(event: types.Message | types.CallbackQuery, bot: Bot, page: int):
    user_id = event.from_user.id
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    refs, total = db.get_referrals_paged(user_id, page=page)
    
    text = f"🤝 **REFERAL TIZIMI**\n\n"
    text += f"Har bir do'stingiz uchun **{REFERRAL_BONUS:,} so'm** olasiz!\n\n"
    text += f"🔗 Havolangiz:\n`{ref_link}`\n\n"
    text += f"👥 Jami takliflar: **{total} ta**\n"
    
    if refs:
        text += "📑 **Oxirgi qo'shilganlar:**\n"
        for i, r in enumerate(refs, 1 + (page-1)*10):
            text += f"{i}. {r['full_name']}\n"
    
    kb = []
    nav_btns = []
    if page > 1:
        nav_btns.append(InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"ref_pg:{page-1}"))
    if total > page * 10:
        nav_btns.append(InlineKeyboardButton(text="Oldinga ➡️", callback_data=f"ref_pg:{page+1}"))
    
    if nav_btns:
        kb.append(nav_btns)
    
    markup = InlineKeyboardMarkup(inline_keyboard=kb)
    
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await event.answer(text, reply_markup=markup, parse_mode="Markdown")

@router.callback_query(F.data.startswith("ref_pg:"))
async def cb_ref_pagination(call: types.CallbackQuery, bot: Bot):
    page = int(call.data.split(":")[1])
    await show_referrals(call, bot, page=page)

# --- BO'LIM 3: DO'KON (CATEGORIZED SHOP) ---

@router.message(F.text == "🛍 Do'kon")
@router.message(Command("shop"))
async def cmd_shop(message: types.Message, bot: Bot):
    # Guruhda ishlatishni cheklash
    if message.chat.type != "private":
        bot_info = await bot.get_me()
        return await message.answer(
            "⚠️ **Do'kon faqat botning o'zida (lichka) ishlaydi!**\n\nSkin sotib olish uchun botga o'ting:",
            reply_markup=get_pm_keyboard(bot_info.username)
        )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍎 Oddiy Skinlar (O'yin puli)", callback_data="shop_cat:simple")],
        [InlineKeyboardButton(text="🍇 Pro Skinlar ($ Monetaga)", callback_data="shop_cat:pro")],
        [InlineKeyboardButton(text="💎 Premium Skinlar (VIP - 30 kun)", callback_data="shop_cat:premium")]
    ])
    await message.answer("🛍 **SKINLAR DO'KONI**\n\nKategoriyani tanlang:", reply_markup=kb)

@router.callback_query(F.data.startswith("shop_cat:"))
async def cb_shop_category(call: types.CallbackQuery):
    cat = call.data.split(":")[1]
    user_id = call.from_user.id
    owned = db.get_user_inventory(user_id)
    
    titles = {"simple": "🍎 ODDY SKINLAR", "pro": "🍇 PRO SKINLAR", "premium": "💎 PREMIUM SKINLAR"}
    text = f"🛒 **{titles[cat]}**\n\nSotib olmoqchi bo'lgan meva ustiga bosing:"
    
    kb = []
    for s in SHOP_SKINS:
        if s['type'] == cat:
            status = "✅" if s['id'] in owned else ""
            if s['currency'] == 'cash':
                price_tag = f"{s['price']:,} so'm"
            else:
                price_tag = f"${s['price']}"
            kb.append([InlineKeyboardButton(text=f"{s['symbol']} {s['name']} - {price_tag} {status}", callback_data=f"buy:{s['id']}")])
    
    kb.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_shop")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "back_to_shop")
async def cb_back_shop(call: types.CallbackQuery, bot: Bot):
    await cmd_shop(call.message, bot)

# --- BO'LIM 4: STATISTIKA VA GLOBAL REYTING ---

@router.message(F.text == "👤 Profilim")
@router.message(Command("stat"))
async def show_stats(message: types.Message, bot: Bot):
    # Guruhda ishlatishni cheklash
    if message.chat.type != "private":
        bot_info = await bot.get_me()
        return await message.answer(
            "⚠️ **Profilingizni faqat botning o'zida ko'ra olasiz!**\n\nMa'lumotlarni ko'rish uchun botga o'ting:",
            reply_markup=get_pm_keyboard(bot_info.username)
        )

    data = db.get_user_profile(message.from_user.id)
    if not data:
        return await message.answer("Xatolik! Botdan to'liq foydalanish uchun /start bosing.")
    
    balance = data['balance']
    if balance < 100000: rank = "O'yinchi 🌱"
    elif balance < 500000: rank = "Tadbirkor 💼"
    elif balance < 2000000: rank = "Millioner 💰"
    else: rank = "Afsonaviy Qirol 👑"

    active_symbol = "Standart"
    for s in SHOP_SKINS:
        if s['id'] == data['active_skin']:
            active_symbol = s['symbol']

    text = (
        f"👤 **PROFIL: {data['full_name']}**\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 O'yin puli: **{balance:,} so'm**\n"
        f"💵 Moneta ($): **${data['coins']}**\n"
        f"🎖 Unvon: **{rank}**\n"
        f"🎨 Skin: **{active_symbol}**\n"
        f"🏆 G'alabalar: **{data['wins']} ta**\n"
        f"━━━━━━━━━━━━━━"
    )
    await message.answer(text)

@router.message(F.text == "🌍 Global Reyting")
@router.message(Command("global"))
async def cmd_global(message: types.Message):
    top_list = db.get_global_top(limit=35)
    if not top_list:
        return await message.answer("Reyting hali shakllanmagan.")

    text = "🌍 **GLOBAL TOP 35 REYTINGI**\n\n"
    for i, row in enumerate(top_list, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        text += f"{medal} **{row['full_name']}** — {row['balance']:,} so'm (${row['coins']})\n"
    
    await message.answer(text)

# --- BO'LIM 5: SKINLARNI BOSHQARISH ---

@router.message(F.text == "🎨 Skinlarim")
@router.message(Command("skinlar"))
async def show_skins_cmd(message: types.Message, bot: Bot):
    # Guruhda ishlatishni cheklash
    if message.chat.type != "private":
        bot_info = await bot.get_me()
        return await message.answer(
            "⚠️ **Skinlarni boshqarish menyusi faqat botning o'zida!**\n\nSkinlarni almashtirish uchun botga o'ting:",
            reply_markup=get_pm_keyboard(bot_info.username)
        )
    await _render_skins_menu(message)

async def _render_skins_menu(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    inventory = db.get_user_inventory_with_time(user_id)
    profile = db.get_user_profile(user_id)
    
    if profile is None: return

    text = "🎨 **INVENTAR (SIZNING SKINLARINGIZ)**\n\nSkinni faollashtirish uchun ustiga bosing:\n"
    kb = []
    
    std_status = "✅" if profile['active_skin'] == 'default' else ""
    kb.append([InlineKeyboardButton(text=f"Standart X/O {std_status}", callback_data="set_skin:default")])
    
    now = datetime.now()
    for item in inventory:
        skin = next((s for s in SHOP_SKINS if s['id'] == item['skin_id']), None)
        if skin:
            status = "✅" if profile['active_skin'] == skin['id'] else ""
            time_left = ""
            if item['expires_at']:
                diff = item['expires_at'] - now
                if diff.days > 0:
                    time_left = f" ({diff.days} kun qoldi)"
                else:
                    hours = diff.seconds // 3600
                    time_left = f" ({hours} soat qoldi)"
            
            kb.append([InlineKeyboardButton(text=f"{skin['symbol']} {skin['name']}{time_left} {status}", callback_data=f"set_skin:{skin['id']}")])
            
    markup = InlineKeyboardMarkup(inline_keyboard=kb)
    if isinstance(event, types.Message):
        await event.answer(text, reply_markup=markup)
    else:
        try:
            await event.message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest:
            pass

# --- BO'LIM 6: CALLBACKS ---

@router.callback_query(F.data.startswith("buy:"))
async def cb_buy_skin(call: types.CallbackQuery):
    skin_id = call.data.split(":")[1]
    res = db.buy_skin(call.from_user.id, skin_id)
    await call.answer(res['msg'], show_alert=True)

@router.callback_query(F.data.startswith("set_skin:"))
async def cb_set_skin(call: types.CallbackQuery):
    skin_id = call.data.split(":")[1]
    db.set_active_skin(call.from_user.id, skin_id)
    await call.answer("Skin o'rnatildi! ✅")
    await _render_skins_menu(call)

# --- BO'LIM 7: O'YINNI BOSHLASH TUGMASI ---

@router.message(F.text == "🎮 O'yinni boshlash")
async def start_game_from_kb(message: types.Message):
    """Asosiy menyudan o'yinni boshlash (Lichkada)"""
    from handlers.game import cmd_game
    await cmd_game(message)