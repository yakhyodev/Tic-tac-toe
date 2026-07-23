from __future__ import annotations

import logging
from datetime import UTC, datetime
from html import escape

from aiogram import Bot, F, Router, types
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from config import REFERRAL_BONUS, SHOP_SKINS
from database import db

router = Router(name="commands")
logger = logging.getLogger(__name__)


def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎮 O'yinni boshlash")],
            [KeyboardButton(text="👤 Profilim"), KeyboardButton(text="🎨 Skinlarim")],
            [KeyboardButton(text="🛍 Do'kon")],
            [KeyboardButton(text="🤝 Referallar"), KeyboardButton(text="🌍 Global reyting")],
        ],
        resize_keyboard=True,
    )


def get_pm_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🤖 Botga o'tish", url=f"https://t.me/{bot_username}")]]
    )


@router.message(CommandStart())
async def cmd_start(message: types.Message, bot: Bot) -> None:
    user = message.from_user
    args = (message.text or "").split(maxsplit=1)
    payload = args[1] if len(args) == 2 else ""
    join_game_id = payload.removeprefix("join_") if payload.startswith("join_") else None
    inviter_id = int(payload) if payload.isdigit() else None
    if inviter_id == user.id:
        inviter_id = None
    await db.register_user(user.id, user.username, user.full_name, inviter_id)

    bot_info = await bot.get_me()
    if message.chat.type != "private":
        await message.answer(
            f"👋 Salom, {escape(user.full_name)}! Matchmaking va do'kon botning shaxsiy chatida ishlaydi.",
            reply_markup=get_pm_keyboard(bot_info.username),
        )
        return

    if join_game_id:
        from handlers.game import join_group_game_from_start

        result = await join_group_game_from_start(bot, user, join_game_id)
        keyboard = None
        if result.get("return_url"):
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🎮 Guruhdagi o'yinga o'tish", url=result["return_url"])]]
            )
        await message.answer(result["message"], reply_markup=keyboard)
        return

    await message.answer(
        f"👋 Salom, <b>{escape(user.full_name)}</b>!\n\n"
        "🎮 Tic-Tac-Toe o'yin botiga xush kelibsiz.\n"
        f"🤝 Taklif qilgan do'stingiz birinchi o'yinini tugatsa, sizga <b>{REFERRAL_BONUS:,} so'm</b> beriladi.\n\n"
        "Boshlash uchun menyudan foydalaning.",
        reply_markup=get_main_keyboard(),
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    await message.answer(
        "<b>Buyruqlar</b>\n\n"
        "/game — o'yin boshlash\n"
        "/cancel — navbat yoki kutilayotgan o'yinni bekor qilish\n"
        "/profile — profil\n"
        "/shop — skinlar do'koni\n"
        "/skins — inventar\n"
        "/ref — referral havola\n"
        "/top — global reyting\n"
        "/rules — o'yin qoidalari"
    )


@router.message(Command("rules"))
async def cmd_rules(message: types.Message) -> None:
    await message.answer(
        "<b>O'yin qoidalari</b>\n\n"
        "<b>Classic:</b> 3×3 doskada ketma-ket 3 ta belgi qo'ygan o'yinchi yutadi.\n\n"
        "<b>Battle:</b> 5×5 doskada 3 o'yinchi qatnashadi. Ketma-ket 4 ta belgi qilganlar 1- va 2-o'rinni oladi. "
        "Doska to'lsa, qolgan o'yinchilar tegishli o'rinni bo'lishadi.\n\n"
        "Har yurish uchun 45 soniya beriladi. Battle'da taymaut qilgan o'yinchi chiqariladi, qolganlar davom etadi."
    )


@router.message(F.text == "🤝 Referallar")
@router.message(Command("ref"))
async def cmd_ref(message: types.Message, bot: Bot) -> None:
    await db.ensure_user_exists(message.from_user.id, message.from_user.full_name, message.from_user.username)
    if message.chat.type != "private":
        bot_info = await bot.get_me()
        try:
            await bot.send_message(message.from_user.id, "Referral ma'lumotingiz:")
        except Exception as error:
            logger.debug("Referral ma'lumotini shaxsiy chatga yuborib bo'lmadi: %s", error)
            await message.answer(
                "Avval botga shaxsiy chatda /start yuboring.", reply_markup=get_pm_keyboard(bot_info.username)
            )
            return
    await show_referrals(message, bot, 1)


async def show_referrals(event: types.Message | types.CallbackQuery, bot: Bot, page: int) -> None:
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={event.from_user.id}"
    referrals, total = await db.get_referrals_paged(event.from_user.id, page)
    lines = [
        "<b>🤝 REFERRAL TIZIMI</b>",
        "",
        f"Do'stingiz birinchi o'yinni tugatgach <b>{REFERRAL_BONUS:,} so'm</b> olasiz.",
        f"Havola: <code>{escape(link)}</code>",
        f"Jami takliflar: <b>{total}</b>",
    ]
    for index, item in enumerate(referrals, 1 + (page - 1) * 10):
        status = "✅" if item["status"] == "rewarded" else "⏳"
        lines.append(f"{index}. {status} {escape(item['full_name'])}")

    navigation: list[InlineKeyboardButton] = []
    if page > 1:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"ref_pg:{page - 1}"))
    if total > page * 10:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"ref_pg:{page + 1}"))
    markup = InlineKeyboardMarkup(inline_keyboard=[navigation] if navigation else [])
    text = "\n".join(lines)
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, reply_markup=markup)
        await event.answer()
    else:
        await event.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("ref_pg:"))
async def cb_ref_pagination(call: types.CallbackQuery, bot: Bot) -> None:
    await show_referrals(call, bot, max(int(call.data.split(":", 1)[1]), 1))


def shop_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🍎 Oddiy", callback_data="shop_cat:simple")],
            [InlineKeyboardButton(text="🍇 Pro", callback_data="shop_cat:pro")],
            [InlineKeyboardButton(text="💎 Premium (30 kun)", callback_data="shop_cat:premium")],
        ]
    )


@router.message(F.text == "🛍 Do'kon")
@router.message(Command("shop"))
async def cmd_shop(message: types.Message, bot: Bot) -> None:
    if message.chat.type != "private":
        bot_info = await bot.get_me()
        await message.answer("Do'kon shaxsiy chatda ishlaydi.", reply_markup=get_pm_keyboard(bot_info.username))
        return
    await message.answer("<b>🛍 SKINLAR DO'KONI</b>\n\nKategoriyani tanlang:", reply_markup=shop_keyboard())


@router.callback_query(F.data.startswith("shop_cat:"))
async def cb_shop_category(call: types.CallbackQuery) -> None:
    category = call.data.split(":", 1)[1]
    if category not in {"simple", "pro", "premium"}:
        await call.answer("Noto'g'ri kategoriya.", show_alert=True)
        return
    owned = await db.get_user_inventory(call.from_user.id)
    titles = {"simple": "🍎 ODDIY", "pro": "🍇 PRO", "premium": "💎 PREMIUM"}
    keyboard = []
    for skin in SHOP_SKINS:
        if skin["type"] != category:
            continue
        status = " ✅" if skin["id"] in owned else ""
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{skin['symbol']} {skin['name']} — {skin['price']:,} so'm{status}",
                    callback_data=f"buy:{skin['id']}",
                )
            ]
        )
    keyboard.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_shop")])
    await call.message.edit_text(
        f"<b>{titles[category]} SKINLAR</b>\n\nSkinni tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
    )
    await call.answer()


@router.callback_query(F.data == "back_to_shop")
async def cb_back_shop(call: types.CallbackQuery) -> None:
    await call.message.edit_text("<b>🛍 SKINLAR DO'KONI</b>\n\nKategoriyani tanlang:", reply_markup=shop_keyboard())
    await call.answer()


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy_skin(call: types.CallbackQuery) -> None:
    result = await db.buy_skin(call.from_user.id, call.data.split(":", 1)[1])
    await call.answer(result["msg"], show_alert=True)


@router.message(F.text == "👤 Profilim")
@router.message(Command("profile", "stat"))
async def show_stats(message: types.Message, bot: Bot) -> None:
    if message.chat.type != "private":
        bot_info = await bot.get_me()
        await message.answer("Profil shaxsiy chatda ko'rsatiladi.", reply_markup=get_pm_keyboard(bot_info.username))
        return
    profile = await db.get_user_profile(message.from_user.id)
    if not profile:
        await message.answer("Avval /start buyrug'ini bosing.")
        return
    active = next((skin["symbol"] for skin in SHOP_SKINS if skin["id"] == profile["active_skin"]), "Standart")
    await message.answer(
        f"<b>👤 {escape(profile['full_name'])}</b>\n\n"
        f"🏅 Reyting: <b>{profile['rating_points']}</b>\n"
        f"💰 O'yin puli: <b>{profile['balance']:,} so'm</b>\n"
        f"🎨 Skin: <b>{active}</b>\n"
        f"🏆 G'alaba: <b>{profile['wins']}</b>\n"
        f"🤝 Durrang: <b>{profile['draws']}</b>\n"
        f"❌ Mag'lubiyat: <b>{profile['losses']}</b>"
    )


@router.message(F.text.in_({"🌍 Global reyting", "🌍 Global Reyting"}))
@router.message(Command("top", "global"))
async def cmd_global(message: types.Message) -> None:
    top_list = await db.get_global_top(35)
    if not top_list:
        await message.answer("Reyting hali shakllanmagan.")
        return
    lines = ["<b>🌍 GLOBAL TOP 35</b>", ""]
    for index, row in enumerate(top_list, 1):
        place = ["🥇", "🥈", "🥉"][index - 1] if index <= 3 else f"{index}."
        lines.append(f"{place} <b>{escape(row['full_name'])}</b> — {row['rating_points']} RP")
    await message.answer("\n".join(lines))


@router.message(F.text == "🎨 Skinlarim")
@router.message(Command("skins", "skinlar"))
async def show_skins_cmd(message: types.Message, bot: Bot) -> None:
    if message.chat.type != "private":
        bot_info = await bot.get_me()
        await message.answer("Inventar shaxsiy chatda ishlaydi.", reply_markup=get_pm_keyboard(bot_info.username))
        return
    await render_skins(message)


async def render_skins(event: types.Message | types.CallbackQuery) -> None:
    inventory = await db.get_user_inventory_with_time(event.from_user.id)
    profile = await db.get_user_profile(event.from_user.id)
    if not profile:
        if isinstance(event, types.CallbackQuery):
            await event.answer("Avval /start buyrug'ini bosing.", show_alert=True)
        return
    keyboard = [
        [
            InlineKeyboardButton(
                text=f"Standart X/O {'✅' if profile['active_skin'] == 'default' else ''}",
                callback_data="set_skin:default",
            )
        ]
    ]
    now = datetime.now(UTC)
    for item in inventory:
        skin = next((skin for skin in SHOP_SKINS if skin["id"] == item["skin_id"]), None)
        if not skin:
            continue
        time_left = ""
        if item["expires_at"]:
            seconds = max(int((item["expires_at"] - now).total_seconds()), 0)
            time_left = f" ({seconds // 86400} kun)" if seconds >= 86400 else f" ({seconds // 3600} soat)"
        active = " ✅" if profile["active_skin"] == skin["id"] else ""
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{skin['symbol']} {skin['name']}{time_left}{active}", callback_data=f"set_skin:{skin['id']}"
                )
            ]
        )
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    text = "<b>🎨 INVENTAR</b>\n\nFaollashtirish uchun skinni tanlang:"
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, reply_markup=markup)
        await event.answer()
    else:
        await event.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("set_skin:"))
async def cb_set_skin(call: types.CallbackQuery) -> None:
    success = await db.set_active_skin(call.from_user.id, call.data.split(":", 1)[1])
    if not success:
        await call.answer("Bu skin sizda mavjud emas yoki muddati tugagan.", show_alert=True)
        return
    await render_skins(call)


@router.message(F.text == "🎮 O'yinni boshlash")
async def start_game_from_keyboard(message: types.Message) -> None:
    from handlers.game import cmd_game

    await cmd_game(message)
