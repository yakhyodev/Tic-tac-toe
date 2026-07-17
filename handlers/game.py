from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from html import escape
from typing import Any

from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import (
    AFK_TIMEOUT,
    AI_MOVE_DELAY,
    DEFAULT_VISUALS,
    FALLBACK_VISUALS,
    MATCHMAKING_WAIT_TIME,
    MAX_PARALLEL_GAMES,
    MODES,
    PREP_GAME_TTL,
    REFERRAL_BONUS,
    ROBOTS,
    SHOP_SKINS,
)
from database import db
from utils.game_logic import (
    EMPTY,
    apply_timeout,
    finalize_placements,
    get_robot_move,
    is_board_full,
    is_winning_move,
    next_available_rank,
)

logger = logging.getLogger(__name__)
router = Router(name="game")

games: dict[str, dict[str, Any]] = {}
matchmaking_queue: dict[str, list[dict[str, Any]]] = {"classic": [], "battle": []}
queue_lock = asyncio.Lock()
game_locks: dict[str, asyncio.Lock] = {}


def _lock(game_id: str) -> asyncio.Lock:
    return game_locks.setdefault(game_id, asyncio.Lock())


def _active_slots(game: dict[str, Any]) -> list[str]:
    return [slot for slot in game["slots"] if slot not in game["placements"]]


def _user_has_active_game(user_id: int) -> bool:
    return any(
        game.get("status") == "active" and any(player["id"] == user_id for player in game["players"].values())
        for game in games.values()
        if "players" in game
    )


def _queued_user(user_id: int) -> bool:
    return any(any(item["id"] == user_id for item in queue) for queue in matchmaking_queue.values())


def get_board_markup(game_id: str, disabled: bool = False) -> InlineKeyboardMarkup | None:
    game = games.get(game_id)
    if not game or "board" not in game:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    for row_index, board_row in enumerate(game["board"]):
        row: list[InlineKeyboardButton] = []
        for column_index, slot in enumerate(board_row):
            visual = "⬜️" if slot is EMPTY else game["players"][slot]["visual"]
            callback = "none" if disabled else f"mv:{game_id}:{row_index}:{column_index}"
            row.append(InlineKeyboardButton(text=visual, callback_data=callback))
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _edit_game_messages(bot: Bot, game: dict[str, Any], text: str, markup: InlineKeyboardMarkup | None) -> None:
    targets = game.get("private_chats", []) if game.get("is_private") else [[game["group_id"], game.get("main_msg_id")]]
    for chat_id, message_id in targets:
        if not message_id:
            continue
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup)
        except Exception as error:
            logger.warning("O'yin xabarini yangilab bo'lmadi game=%s chat=%s: %s", game["id"], chat_id, error)


async def update_ui(bot: Bot, game_id: str) -> None:
    game = games.get(game_id)
    if not game or game.get("status") != "active":
        return
    current_slot = game["slots"][game["turn_idx"]]
    current_player = game["players"][current_slot]
    lines = [f"<b>🎮 {game['mode'].upper()}</b>", f"📍 {escape(game['chat_name'])}", ""]
    for slot in game["slots"]:
        player = game["players"][slot]
        if slot in game["placements"]:
            status = f"🏅 {game['placements'][slot]}-o'rin"
        else:
            status = "➡️ navbat" if slot == current_slot else ""
        lines.append(f"{player['visual']} {escape(player['name'])} {status}")
    lines.extend(["", f"⏳ Navbat: <b>{current_player['visual']} {escape(current_player['name'])}</b>"])
    if game.get("is_private"):
        lines.append("💬 Oddiy matn yuborsangiz, u raqib(lar)ga uzatiladi.")
    await _edit_game_messages(bot, game, "\n".join(lines), get_board_markup(game_id))


@router.callback_query(F.data == "none")
async def cb_none(call: types.CallbackQuery) -> None:
    await call.answer("O'yin yakunlangan.")


@router.message(Command("game"))
async def cmd_game(message: types.Message) -> None:
    await db.ensure_user_exists(message.from_user.id, message.from_user.full_name, message.from_user.username)
    if _user_has_active_game(message.from_user.id) or _queued_user(message.from_user.id):
        await message.answer("Sizda faol o'yin yoki matchmaking navbati mavjud. Bekor qilish: /cancel")
        return
    if message.chat.type != "private":
        count = sum(
            1
            for game in games.values()
            if game.get("group_id") == message.chat.id and game.get("status") in {"waiting", "active"}
        )
        if count >= MAX_PARALLEL_GAMES:
            await message.answer(f"Bu guruhda {MAX_PARALLEL_GAMES} ta parallel o'yin limiti to'lgan.")
            return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Classic (2 kishi)", callback_data=f"setup:classic:{message.from_user.id}")],
            [InlineKeyboardButton(text="⚔️ Battle (3 kishi)", callback_data=f"setup:battle:{message.from_user.id}")],
        ]
    )
    await message.answer("<b>O'yin rejimini tanlang:</b>", reply_markup=keyboard)


@router.callback_query(F.data.startswith("setup:"))
async def cb_setup(call: types.CallbackQuery, bot: Bot) -> None:
    try:
        _, mode, creator = call.data.split(":", 2)
    except ValueError:
        await call.answer("Noto'g'ri so'rov.", show_alert=True)
        return
    if mode not in MODES or int(creator) != call.from_user.id:
        await call.answer("Bu tugma o'yin yaratuvchisiga tegishli.", show_alert=True)
        return
    if _user_has_active_game(call.from_user.id) or _queued_user(call.from_user.id):
        await call.answer("Siz allaqachon o'yin yoki navbatdasiz.", show_alert=True)
        return

    await db.ensure_user_exists(call.from_user.id, call.from_user.full_name, call.from_user.username)
    await call.answer()
    if call.message.chat.type == "private":
        await call.message.edit_text(
            f"🔎 <b>{MODES[mode]['name']}</b> uchun raqib qidirilmoqda…\nBekor qilish: /cancel"
        )
        await handle_matchmaking(bot, call.from_user, mode, call.message.message_id)
        return

    prep_id = str(uuid.uuid4())
    game = {
        "id": prep_id,
        "status": "waiting",
        "mode": mode,
        "req": MODES[mode]["players"],
        "players_list": [
            {"id": call.from_user.id, "name": call.from_user.full_name, "username": call.from_user.username}
        ],
        "creator_id": call.from_user.id,
        "group_id": call.message.chat.id,
        "main_msg_id": call.message.message_id,
        "chat_name": call.message.chat.title or "Guruh",
        "created_at": time.time(),
    }
    games[prep_id] = game
    await db.save_game(prep_id, "waiting", game)
    await _render_waiting_group(call.message, game)


async def _render_waiting_group(message: types.Message, game: dict[str, Any]) -> None:
    names = "\n".join(f"{index}. {escape(player['name'])}" for index, player in enumerate(game["players_list"], 1))
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Qo'shilish", callback_data=f"join:{game['id']}")],
            [InlineKeyboardButton(text="🤖 Robot qo'shish", callback_data=f"add_bot:{game['id']}")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_prep:{game['id']}")],
        ]
    )
    await message.edit_text(
        f"<b>🎮 {MODES[game['mode']]['name']}</b>\n\n{names}\n\nKutilmoqda…",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("join:"))
async def cb_join(call: types.CallbackQuery, bot: Bot) -> None:
    prep_id = call.data.split(":", 1)[1]
    async with _lock(prep_id):
        game = games.get(prep_id)
        if not game or game.get("status") != "waiting":
            await call.answer("O'yin boshlangan yoki bekor qilingan.", show_alert=True)
            return
        if any(player["id"] == call.from_user.id for player in game["players_list"]):
            await call.answer("Siz allaqachon qo'shilgansiz.", show_alert=True)
            return
        if _user_has_active_game(call.from_user.id) or _queued_user(call.from_user.id):
            await call.answer("Siz boshqa o'yin yoki navbatdasiz.", show_alert=True)
            return
        await db.ensure_user_exists(call.from_user.id, call.from_user.full_name, call.from_user.username)
        game["players_list"].append(
            {"id": call.from_user.id, "name": call.from_user.full_name, "username": call.from_user.username}
        )
        await call.answer("Qo'shildingiz.")
        if len(game["players_list"]) >= game["req"]:
            await call.message.edit_text("🎮 O'yin boshlanmoqda…")
            await start_real_game(bot, prep_id=prep_id)
        else:
            await db.save_game(prep_id, "waiting", game)
            await _render_waiting_group(call.message, game)


@router.callback_query(F.data.startswith("add_bot:"))
async def cb_add_bot(call: types.CallbackQuery, bot: Bot) -> None:
    prep_id = call.data.split(":", 1)[1]
    async with _lock(prep_id):
        game = games.get(prep_id)
        if not game or game.get("status") != "waiting":
            await call.answer("O'yin mavjud emas.", show_alert=True)
            return
        if game["creator_id"] != call.from_user.id:
            await call.answer("Faqat yaratuvchi robot qo'sha oladi.", show_alert=True)
            return
        used = {player["id"] for player in game["players_list"]}
        available = [robot for robot in ROBOTS if robot["id"] not in used]
        while len(game["players_list"]) < game["req"] and available:
            robot = random.choice(available)
            available.remove(robot)
            game["players_list"].append({"id": robot["id"], "name": robot["name"], "username": None})
        await call.answer()
        await call.message.edit_text("🤖 Robot qo'shildi. O'yin boshlanmoqda…")
        await start_real_game(bot, prep_id=prep_id)


@router.callback_query(F.data.startswith("cancel_prep:"))
async def cb_cancel_prep(call: types.CallbackQuery) -> None:
    prep_id = call.data.split(":", 1)[1]
    game = games.get(prep_id)
    if not game or game.get("creator_id") != call.from_user.id:
        await call.answer("Faqat yaratuvchi bekor qila oladi.", show_alert=True)
        return
    game["status"] = "cancelled"
    await db.save_game(prep_id, "cancelled", game)
    games.pop(prep_id, None)
    game_locks.pop(prep_id, None)
    await call.message.edit_text("❌ O'yin bekor qilindi.")
    await call.answer()


async def handle_matchmaking(bot: Bot, user: types.User, mode: str, message_id: int) -> None:
    item = {"id": user.id, "name": user.full_name, "username": user.username, "message_id": message_id}
    async with queue_lock:
        if _queued_user(user.id):
            return
        matchmaking_queue[mode].append(item)

    await asyncio.sleep(MATCHMAKING_WAIT_TIME)
    group: list[dict[str, Any]] | None = None
    async with queue_lock:
        if item not in matchmaking_queue[mode]:
            return
        required = MODES[mode]["players"]
        if len(matchmaking_queue[mode]) >= required:
            group = matchmaking_queue[mode][:required]
            del matchmaking_queue[mode][:required]
        else:
            matchmaking_queue[mode].remove(item)
            group = [item]

    while len(group) < MODES[mode]["players"]:
        used = {player["id"] for player in group}
        robot = random.choice([robot for robot in ROBOTS if robot["id"] not in used])
        group.append({"id": robot["id"], "name": robot["name"], "username": None})
    try:
        await bot.edit_message_text("🤝 Match tayyor. O'yin boshlanmoqda…", user.id, message_id)
    except Exception as error:
        logger.debug("Matchmaking xabarini yangilab bo'lmadi: %s", error)
    await start_real_game(bot, matchmaking_data=group, mode=mode)


async def _visual_for_player(user_id: int, used: set[str], default_index: int) -> str:
    visual = DEFAULT_VISUALS[default_index]
    if user_id > 0:
        profile = await db.get_user_profile(user_id)
        inventory = await db.get_user_inventory_with_time(user_id) if profile else []
        owned = {item["skin_id"] for item in inventory}
        preferred = next(
            (
                skin["symbol"]
                for skin in SHOP_SKINS
                if profile and skin["id"] == profile["active_skin"] and skin["id"] in owned
            ),
            None,
        )
        if preferred and preferred not in used:
            visual = preferred
    if visual in used:
        visual = next(symbol for symbol in DEFAULT_VISUALS + FALLBACK_VISUALS if symbol not in used)
    return visual


async def start_real_game(
    bot: Bot,
    prep_id: str | None = None,
    matchmaking_data: list[dict[str, Any]] | None = None,
    mode: str | None = None,
) -> None:
    if matchmaking_data is not None:
        players_list = list(matchmaking_data)
        current_mode = mode or "classic"
        is_private = True
        group_id = players_list[0]["id"]
        chat_name = "Matchmaking"
    else:
        prep = games.get(prep_id or "")
        if not prep:
            return
        players_list = list(prep["players_list"])
        current_mode = prep["mode"]
        is_private = False
        group_id = prep["group_id"]
        chat_name = prep["chat_name"]
        await db.delete_game(prep["id"])
        games.pop(prep["id"], None)

    random.shuffle(players_list)
    game_id = str(uuid.uuid4())
    slots = [f"p{index}" for index in range(len(players_list))]
    players: dict[str, dict[str, Any]] = {}
    used_visuals: set[str] = set()
    for index, (slot, source) in enumerate(zip(slots, players_list, strict=True)):
        visual = await _visual_for_player(source["id"], used_visuals, index)
        used_visuals.add(visual)
        players[slot] = {"id": source["id"], "name": source["name"], "visual": visual}

    size = MODES[current_mode]["size"]
    game = {
        "id": game_id,
        "status": "active",
        "mode": current_mode,
        "board": [[EMPTY for _ in range(size)] for _ in range(size)],
        "players": players,
        "slots": slots,
        "turn_idx": 0,
        "placements": {},
        "draw_slots": [],
        "draw_type": None,
        "group_id": group_id,
        "chat_name": chat_name,
        "is_private": is_private,
        "private_chats": [],
        "last_move": time.time(),
        "created_at": time.time(),
    }
    games[game_id] = game

    if is_private:
        for slot in slots:
            player = players[slot]
            if player["id"] > 0:
                message = await bot.send_message(player["id"], f"🎮 O'yin boshlandi. Belgingiz: {player['visual']}")
                game["private_chats"].append([player["id"], message.message_id])
    else:
        message = await bot.send_message(group_id, "🎮 O'yin boshlanmoqda…")
        game["main_msg_id"] = message.message_id

    await db.save_game(game_id, "active", game)
    await update_ui(bot, game_id)
    _schedule_robot_if_needed(bot, game_id)


def _schedule_robot_if_needed(bot: Bot, game_id: str) -> None:
    game = games.get(game_id)
    if not game or game.get("status") != "active":
        return
    slot = game["slots"][game["turn_idx"]]
    if game["players"][slot]["id"] < 0:
        asyncio.create_task(_delayed_robot_turn(bot, game_id))


async def _delayed_robot_turn(bot: Bot, game_id: str) -> None:
    await asyncio.sleep(AI_MOVE_DELAY)
    try:
        await process_robot_turn(bot, game_id)
    except Exception:
        logger.exception("Robot yurishida xato game=%s", game_id)


def _next_turn(game: dict[str, Any]) -> None:
    for _ in game["slots"]:
        game["turn_idx"] = (game["turn_idx"] + 1) % len(game["slots"])
        if game["slots"][game["turn_idx"]] not in game["placements"]:
            return


def _resolve_after_move(game: dict[str, Any], row: int, column: int, slot: str) -> bool:
    if is_winning_move(game["board"], row, column, slot, MODES[game["mode"]]["win_len"]):
        game["placements"][slot] = next_available_rank(game["placements"], len(game["slots"]))

    active = _active_slots(game)
    if len(active) <= 1:
        finalize_placements(game["slots"], game["placements"])
        return True

    if is_board_full(game["board"]):
        game["draw_slots"] = active
        game["draw_type"] = "partial" if any(rank == 1 for rank in game["placements"].values()) else "full"
        if game["placements"]:
            rank = next_available_rank(game["placements"], len(game["slots"]))
            for active_slot in active:
                game["placements"][active_slot] = rank
        return True

    _next_turn(game)
    return False


@router.callback_query(F.data.startswith("mv:"))
async def cb_move(call: types.CallbackQuery, bot: Bot) -> None:
    try:
        _, game_id, row_text, column_text = call.data.split(":", 3)
        row, column = int(row_text), int(column_text)
    except (ValueError, TypeError):
        await call.answer("Noto'g'ri yurish.", show_alert=True)
        return

    should_schedule_robot = False
    async with _lock(game_id):
        game = games.get(game_id)
        if not game or game.get("status") != "active":
            await call.answer("O'yin yakunlangan.", show_alert=True)
            return
        size = len(game["board"])
        if not (0 <= row < size and 0 <= column < size) or game["board"][row][column] is not EMPTY:
            await call.answer("Bu katak band.", show_alert=True)
            return
        slot = game["slots"][game["turn_idx"]]
        if game["players"][slot]["id"] != call.from_user.id:
            await call.answer("Navbatingiz emas.", show_alert=True)
            return

        await call.answer()
        game["board"][row][column] = slot
        game["last_move"] = time.time()
        finished = _resolve_after_move(game, row, column, slot)
        if finished:
            await finish_game(bot, game_id)
        else:
            await db.save_game(game_id, "active", game)
            await update_ui(bot, game_id)
            should_schedule_robot = True
    if should_schedule_robot:
        _schedule_robot_if_needed(bot, game_id)


async def process_robot_turn(bot: Bot, game_id: str) -> None:
    should_schedule_robot = False
    async with _lock(game_id):
        game = games.get(game_id)
        if not game or game.get("status") != "active":
            return
        slot = game["slots"][game["turn_idx"]]
        if game["players"][slot]["id"] >= 0:
            return
        opponents = [active for active in _active_slots(game) if active != slot]
        move = get_robot_move(game["board"], len(game["board"]), MODES[game["mode"]]["win_len"], slot, opponents)
        if move is None:
            game["draw_slots"] = _active_slots(game)
            game["draw_type"] = "full" if not game["placements"] else "partial"
            await finish_game(bot, game_id)
            return
        row, column = move
        game["board"][row][column] = slot
        game["last_move"] = time.time()
        if _resolve_after_move(game, row, column, slot):
            await finish_game(bot, game_id)
        else:
            await db.save_game(game_id, "active", game)
            await update_ui(bot, game_id)
            should_schedule_robot = True
    if should_schedule_robot:
        _schedule_robot_if_needed(bot, game_id)


@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, bot: Bot) -> None:
    user_id = message.from_user.id
    removed_from_queue = False
    async with queue_lock:
        for queue in matchmaking_queue.values():
            before = len(queue)
            queue[:] = [item for item in queue if item["id"] != user_id]
            removed_from_queue = removed_from_queue or len(queue) != before
    if removed_from_queue:
        await message.answer("Matchmaking navbati bekor qilindi.")
        return

    for game_id, game in list(games.items()):
        if game.get("status") == "waiting" and any(player["id"] == user_id for player in game["players_list"]):
            if game["creator_id"] == user_id:
                game["status"] = "cancelled"
                await db.save_game(game_id, "cancelled", game)
                games.pop(game_id, None)
                await message.answer("Kutilayotgan o'yin bekor qilindi.")
            else:
                game["players_list"] = [player for player in game["players_list"] if player["id"] != user_id]
                await db.save_game(game_id, "waiting", game)
                await message.answer("O'yindan chiqdingiz.")
            return
        if game.get("status") == "active":
            slot = next((slot for slot, player in game["players"].items() if player["id"] == user_id), None)
            if slot and slot not in game["placements"]:
                await _handle_timeout(bot, game_id, slot, reason="O'yindan chiqdi")
                await message.answer("Siz o'yindan chiqdingiz va texnik mag'lubiyat olasiz.")
                return
    await message.answer("Bekor qilinadigan navbat yoki o'yin topilmadi.")


@router.message(F.chat.type == "private", ~F.text.startswith("/"))
async def private_messenger(message: types.Message) -> None:
    game = next(
        (
            item
            for item in games.values()
            if item.get("status") == "active"
            and item.get("is_private")
            and any(player["id"] == message.from_user.id for player in item["players"].values())
        ),
        None,
    )
    if not game:
        await message.answer("Buyruqlar ro'yxati uchun /help ni bosing.")
        return
    text = escape(message.text or "")[:1000]
    for player in game["players"].values():
        if player["id"] > 0 and player["id"] != message.from_user.id:
            try:
                await message.bot.send_message(player["id"], f"💬 <b>Raqib:</b> {text}")
            except Exception as error:
                logger.warning("Raqib xabarini yuborib bo'lmadi: %s", error)


def _build_participants(game: dict[str, Any]) -> list[dict[str, Any]]:
    participants = []
    draw_slots = set(game.get("draw_slots", []))
    for slot in game["slots"]:
        rank = game["placements"].get(slot, 99)
        participants.append(
            {
                "user_id": game["players"][slot]["id"],
                "rank": rank,
                "is_draw": slot in draw_slots,
                "draw_type": game.get("draw_type") if slot in draw_slots else None,
            }
        )
    return participants


async def finish_game(bot: Bot, game_id: str) -> None:
    game = games.get(game_id)
    if not game or game.get("status") != "active":
        return
    game["status"] = "finishing"
    try:
        settlement = await db.process_game_results(game_id, game["mode"], _build_participants(game))
    except Exception:
        game["status"] = "active"
        await db.save_game(game_id, "active", game)
        logger.exception("O'yin natijasini atomar saqlashda xato game=%s", game_id)
        return
    result_by_id = {item["user_id"]: item for item in settlement["results"]}
    lines = ["<b>🏁 O'YIN YAKUNLANDI</b>", ""]
    for slot in game["slots"]:
        player = game["players"][slot]
        result = result_by_id.get(player["id"], {"reward": 0, "rank": 99, "is_draw": False})
        if result["is_draw"]:
            status = f"🤝 {result['rank']}-o'rin durrang" if result["rank"] != 99 else "🤝 Durrang"
        elif result["rank"] <= len(game["slots"]):
            status = f"🏅 {result['rank']}-o'rin"
        else:
            status = "❌ Mag'lub"
        lines.append(f"{player['visual']} {escape(player['name'])}: {status} — <b>{result['reward']:,} so'm</b>")
    summary = "\n".join(lines)
    await _edit_game_messages(bot, game, summary, get_board_markup(game_id, disabled=True))

    if not game.get("is_private"):
        for slot in game["slots"]:
            player = game["players"][slot]
            if player["id"] > 0:
                try:
                    await bot.send_message(player["id"], summary)
                except Exception as error:
                    logger.debug("Guruh o'yini natijasini shaxsiy chatga yuborib bo'lmadi: %s", error)
    for referral in settlement["referrals"]:
        try:
            await bot.send_message(
                referral["inviter_id"],
                f"🎉 Taklif qilgan do'stingiz birinchi o'yinini tugatdi. Hisobingizga <b>{REFERRAL_BONUS:,} so'm</b> qo'shildi.",
            )
        except Exception as error:
            logger.debug("Referral bildirishnomasini yuborib bo'lmadi: %s", error)

    game["status"] = "finished"
    await db.delete_game(game_id)
    games.pop(game_id, None)
    game_locks.pop(game_id, None)


async def _handle_timeout(bot: Bot, game_id: str, slot: str, reason: str = "Vaqt tugadi") -> None:
    async with _lock(game_id):
        game = games.get(game_id)
        if not game or game.get("status") != "active" or slot in game["placements"]:
            return
        apply_timeout(game["slots"], game["placements"], slot)
        active = _active_slots(game)
        if len(active) <= 1:
            finalize_placements(game["slots"], game["placements"])
            await finish_game(bot, game_id)
            return
        game["last_move"] = time.time()
        current_slot = game["slots"][game["turn_idx"]]
        if current_slot in game["placements"]:
            _next_turn(game)
        await db.save_game(game_id, "active", game)
        try:
            await bot.send_message(
                game["group_id"] if not game["is_private"] else game["players"][slot]["id"],
                f"⌛️ {escape(game['players'][slot]['name'])}: {reason}.",
            )
        except Exception as error:
            logger.debug("Taymaut xabarini yuborib bo'lmadi: %s", error)
        await update_ui(bot, game_id)
    _schedule_robot_if_needed(bot, game_id)


async def restore_persisted_games() -> int:
    restored = await db.load_open_games()
    now = time.time()
    for game_id, game in restored.items():
        if game.get("status") == "active":
            # Deploy davomida o'tgan vaqt o'yinchiga texnik mag'lubiyat bo'lmaydi.
            game["last_move"] = now
            await db.save_game(game_id, "active", game)
    games.update(restored)
    return len(restored)


async def game_watchdog(bot: Bot) -> None:
    while True:
        await asyncio.sleep(3)
        now = time.time()
        for game_id, game in list(games.items()):
            try:
                if game.get("status") == "waiting" and now - game.get("created_at", now) >= PREP_GAME_TTL:
                    game["status"] = "cancelled"
                    await db.save_game(game_id, "cancelled", game)
                    try:
                        await bot.edit_message_text(
                            "⌛️ O'yin yig'ish vaqti tugadi.",
                            chat_id=game["group_id"],
                            message_id=game.get("main_msg_id"),
                        )
                    except Exception as error:
                        logger.debug("Eskirgan o'yin xabarini yangilab bo'lmadi: %s", error)
                    games.pop(game_id, None)
                    game_locks.pop(game_id, None)
                    continue
                if game.get("status") != "active":
                    continue
                slot = game["slots"][game["turn_idx"]]
                if game["players"][slot]["id"] < 0:
                    if now - game["last_move"] >= max(AI_MOVE_DELAY + 1, 3):
                        await process_robot_turn(bot, game_id)
                elif now - game["last_move"] >= AFK_TIMEOUT:
                    await _handle_timeout(bot, game_id, slot)
            except Exception:
                logger.exception("Watchdog siklida xato game=%s", game_id)
