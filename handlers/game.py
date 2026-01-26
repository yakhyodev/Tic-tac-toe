import asyncio
import random
import time
import logging
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

# Ichki modullar
from database import db
from config import MODES, MAX_PARALLEL_GAMES, ROBOTS, AI_MOVE_DELAY, SHOP_SKINS, MATCHMAKING_WAIT_TIME
from utils.game_logic import check_winner, get_robot_move, is_game_over

router = Router()

# O'yinlar xotirasi va Matchmaking navbati
games = {} 
matchmaking_queue = {"classic": [], "battle": []}
queue_lock = asyncio.Lock()

# --- BO'LIM 1: YORDAMCHI INTERFEYS FUNKSIYALARI ---

def get_board_markup(game_id, disabled=False):
    """Doska markupini yaratish"""
    if game_id not in games:
        return None
    
    g = games[game_id]
    size = len(g['board'])
    btns = []
    for r in range(size):
        row = []
        for c in range(size):
            char = g['board'][r][c]
            text = '⬜️' if char == ' ' else char
            
            if disabled:
                row.append(InlineKeyboardButton(text=text, callback_data="none"))
            else:
                row.append(InlineKeyboardButton(text=text, callback_data=f"mv:{game_id}:{r}:{c}"))
        btns.append(row)
    return InlineKeyboardMarkup(inline_keyboard=btns)

async def update_ui(bot: Bot, game_id):
    """O'yin xabarini yangilash"""
    if game_id not in games:
        return
    
    g = games[game_id]
    curr_s = g['symbols'][g['turn_idx']]
    curr_p = g['players'][curr_s]
    
    text = f"🎮 **{g['mode'].upper()} REJIMI**\n"
    text += f"📍 {g['chat_name']}\n\n"
    for s in g['symbols']:
        status = "➡️" if s == curr_s else "  "
        p_name = g['players'][s]['name']
        winner_status = ""
        if s in g['winners']:
            winner_status = f" [🏆 {g['winners'].index(s)+1}-o'rin]"
        text += f"{status} {s}: {p_name}{winner_status}\n"
    
    text += f"\n⏳ Navbat: {curr_s} **{curr_p['name']}**"
    if g.get('is_private'):
        text += "\n\n💬 *Raqibga xabar yuborish uchun shunchaki matn yozing.*"
    
    markup = get_board_markup(game_id)
    if g.get('is_private'):
        targets = g['private_chats']
    else:
        targets = [(g['group_id'], g['main_msg_id'])]
    
    for chat_id, msg_id in targets:
        try:
            await bot.edit_message_text(
                chat_id=chat_id, 
                message_id=msg_id, 
                text=text, 
                reply_markup=markup
            )
        except Exception:
            pass

@router.callback_query(F.data == "none")
async def cb_none(call: types.CallbackQuery):
    await call.answer()

# --- BO'LIM 2: O'YIN TAYYORLASH VA QO'SHILISH ---

@router.message(Command("game"))
async def cmd_game(message: types.Message):
    """O'yinni boshlash buyrug'i"""
    if message.chat.type != "private":
        chat_games = [gid for gid, g in games.items() if g.get('group_id') == message.chat.id]
        if len(chat_games) >= MAX_PARALLEL_GAMES:
            return await message.answer(f"⚠️ Limit: {MAX_PARALLEL_GAMES} ta parallel o'yin.")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 2 kishilik (Classic)", callback_data=f"setup:2:{message.from_user.id}")],
        [InlineKeyboardButton(text="⚔️ 3 kishilik (Battle)", callback_data=f"setup:3:{message.from_user.id}")]
    ])
    await message.answer("🎮 **O'yin rejimini tanlang:**", reply_markup=kb)

@router.callback_query(F.data.startswith("setup:"))
async def cb_setup(call: types.CallbackQuery, bot: Bot):
    _, count, creator_id = call.data.split(":")
    if str(call.from_user.id) != creator_id:
        return await call.answer("Faqat yaratuvchi tanlay oladi!", show_alert=True)
    
    if count == '2':
        mode_key = 'classic'
    else:
        mode_key = 'battle'
    
    if call.message.chat.type == "private":
        await call.message.edit_text(f"🔍 **{count} kishilik** raqib qidirilmoqda...")
        await handle_matchmaking(bot, call.from_user, mode_key, int(count), call.message)
        return

    prep_id = f"prep_{int(time.time())}_{call.from_user.id}"
    games[prep_id] = {
        'mode': mode_key, 
        'req': int(count),
        'players_list': [{"id": call.from_user.id, "name": call.from_user.full_name}], 
        'creator_id': int(creator_id),
        'group_id': call.message.chat.id, 
        'chat_name': call.message.chat.title or "Guruh"
    }
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Qo'shilish", callback_data=f"join:{prep_id}")],
        [InlineKeyboardButton(text="🤖 Robot qo'shish", callback_data=f"add_bot:{prep_id}")]
    ])
    await call.message.edit_text(
        f"🎮 **{count} kishilik o'yin!**\n\n1. {call.from_user.full_name}\n\nKutilmoqda...", 
        reply_markup=kb
    )

@router.callback_query(F.data.startswith("join:"))
async def cb_join(call: types.CallbackQuery, bot: Bot):
    """Guruhda o'yinga qo'shilish"""
    prep_id = call.data.split(":")[1]
    if prep_id not in games:
        return await call.answer("O'yin allaqachon boshlangan yoki bekor qilingan.")
    
    g = games[prep_id]
    if any(p['id'] == call.from_user.id for p in g['players_list']):
        return await call.answer("Siz allaqachon qo'shilgansiz!", show_alert=True)
    
    if len(g['players_list']) >= g['req']:
        return await call.answer("O'yin to'lgan!")

    # MUHIM: Foydalanuvchi start bosmagan bo'lsa ham bazaga yozish
    db.ensure_user_exists(
        user_id=call.from_user.id, 
        full_name=call.from_user.full_name, 
        username=call.from_user.username
    )

    g['players_list'].append({"id": call.from_user.id, "name": call.from_user.full_name})
    
    player_names = ""
    for idx, p in enumerate(g['players_list'], 1):
        player_names += f"{idx}. {p['name']}\n"
    
    if len(g['players_list']) >= g['req']:
        await call.message.edit_text(f"🎮 **O'yin boshlanmoqda!**\n\n{player_names}")
        await start_real_game(bot, prep_id)
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Qo'shilish", callback_data=f"join:{prep_id}")],
            [InlineKeyboardButton(text="🤖 Robot qo'shish", callback_data=f"add_bot:{prep_id}")]
        ])
        await call.message.edit_text(f"🎮 **{g['req']} kishilik o'yin!**\n\n{player_names}\nKutilmoqda...", reply_markup=kb)
        await call.answer("Qo'shildingiz! ✅")

@router.callback_query(F.data.startswith("add_bot:"))
async def cb_add_bot(call: types.CallbackQuery, bot: Bot):
    """Guruhda robot qo'shish"""
    prep_id = call.data.split(":")[1]
    if prep_id not in games:
        return await call.answer("Xatolik!")
    
    g = games[prep_id]
    if call.from_user.id != g['creator_id']:
        return await call.answer("Faqat yaratuvchi robot qo'sha oladi!", show_alert=True)
    
    while len(g['players_list']) < g['req']:
        current_ids = [p['id'] for p in g['players_list']]
        available_robots = [r for r in ROBOTS if r['id'] not in current_ids]
        if not available_robots:
            break
        robot = random.choice(available_robots)
        g['players_list'].append({"id": robot['id'], "name": robot['name']})

    await call.message.edit_text("🤖 Robotlar qo'shildi. O'yin boshlanmoqda...")
    await start_real_game(bot, prep_id)

# --- BO'LIM 3: MATCHMAKING VA O'YIN BOSHLASH ---

async def handle_matchmaking(bot: Bot, user, mode, req_count, original_msg):
    user_data = {"id": user.id, "name": user.full_name, "msg_id": original_msg.message_id}
    async with queue_lock:
        matchmaking_queue[mode].append(user_data)
    
    await asyncio.sleep(MATCHMAKING_WAIT_TIME)
    
    async with queue_lock:
        if user_data not in matchmaking_queue[mode]:
            return
        
        if len(matchmaking_queue[mode]) >= req_count:
            group = matchmaking_queue[mode][:req_count]
            for p in group:
                matchmaking_queue[mode].remove(p)
            await start_real_game(bot, None, matchmaking_data=group, mode=mode)
        else:
            matchmaking_queue[mode].remove(user_data)
            group = [user_data]
            while len(group) < req_count:
                robot = random.choice(ROBOTS)
                if robot['id'] not in [p['id'] for p in group]:
                    group.append({"id": robot['id'], "name": robot['name'], "is_robot": True})
            
            try:
                await bot.edit_message_text(
                    "🤝 Raqib topilmadi. Robot bilan o'yin boshlanmoqda!", 
                    chat_id=user.id, 
                    message_id=original_msg.message_id
                )
            except Exception:
                pass
            await start_real_game(bot, None, matchmaking_data=group, mode=mode)

async def start_real_game(bot: Bot, prep_id, matchmaking_data=None, mode=None):
    if matchmaking_data:
        players_list = matchmaking_data
        chat_name = "Matchmaking"
        is_private = True
        group_id = matchmaking_data[0]['id']
        current_mode = mode
    else:
        g = games[prep_id]
        players_list = g['players_list']
        chat_name = g['chat_name']
        is_private = False
        group_id = g['group_id']
        current_mode = g['mode']
        del games[prep_id]

    game_id = f"{current_mode}_{int(time.time())}"
    symbols = MODES[current_mode]['symbols']
    random.shuffle(players_list)
    
    player_map = {}
    used_visual_symbols = []

    for i, p_info in enumerate(players_list):
        uid = p_info['id']
        final_symbol = symbols[i]
        
        if uid < 0:
            name = p_info['name']
            active_skin_id = 'default'
            inventory = []
        else:
            profile = db.get_user_profile(uid)
            if profile is None:
                name = p_info['name']
                active_skin_id = 'default'
                inventory = []
            else:
                name = profile['full_name']
                active_skin_id = profile['active_skin']
                inventory = db.get_user_inventory_with_time(uid)
            
            owned_skins_full = []
            for item in inventory:
                skin_data = next((s for s in SHOP_SKINS if s['id'] == item['skin_id']), None)
                if skin_data:
                    owned_skins_full.append(skin_data)
            
            type_order = {'premium': 0, 'pro': 1, 'simple': 2}
            owned_skins_full.sort(key=lambda x: type_order.get(x['type'], 3))

            active_skin_data = next((s for s in SHOP_SKINS if s['id'] == active_skin_id), None)
            
            if active_skin_data and active_skin_data['symbol'] not in used_visual_symbols:
                final_symbol = active_skin_data['symbol']
            else:
                found_backup = False
                for skin in owned_skins_full:
                    if skin['symbol'] not in used_visual_symbols:
                        final_symbol = skin['symbol']
                        found_backup = True
                        break
                if not found_backup:
                    for backup_s in ["💎", "🌟", "🔥", "🍀", "🌀"]:
                        if backup_s not in used_visual_symbols:
                            final_symbol = backup_s
                            found_backup = True
                            break
                    if not found_backup:
                        final_symbol = symbols[i]

        used_visual_symbols.append(final_symbol)
        player_map[symbols[i]] = {'id': uid, 'name': name, 'symbol': final_symbol}

    size = MODES[current_mode]['size']
    games[game_id] = {
        'board': [[' ']*size for _ in range(size)],
        'players': player_map, 
        'symbols': symbols,
        'turn_idx': 0, 
        'mode': current_mode, 
        'winners': [],
        'group_id': group_id, 
        'chat_name': chat_name,
        'active': True, 
        'last_move': time.time(), 
        'size': size,
        'is_private': is_private, 
        'private_chats': []
    }

    if is_private:
        for p_info in players_list:
            p_id = p_info['id']
            if p_id > 0:
                s_info = next(player_map[s]['symbol'] for s in symbols if player_map[s]['id'] == p_id)
                msg = await bot.send_message(p_id, f"🎮 O'yin boshlandi! Belgingiz: {s_info}")
                games[game_id]['private_chats'].append((p_id, msg.message_id))
    else:
        msg = await bot.send_message(group_id, "🎮 O'yin boshlanmoqda...")
        games[game_id]['main_msg_id'] = msg.message_id

    await update_ui(bot, game_id)
    
    first_symbol = symbols[0]
    if player_map[first_symbol]['id'] < 0:
        await asyncio.sleep(AI_MOVE_DELAY)
        await process_robot_turn(bot, game_id)

# --- BO'LIM 4: YURISH VA MESSENGER ---

@router.message(F.chat.type == "private", ~F.text.startswith("/"))
async def private_messenger(message: types.Message):
    user_id = message.from_user.id
    active_game = next((g for g in games.values() if g.get('is_private') and any(p['id'] == user_id for p in g['players'].values())), None)
    if active_game:
        for s in active_game['symbols']:
            opponent_id = active_game['players'][s]['id']
            if opponent_id > 0 and opponent_id != user_id:
                try:
                    await message.bot.send_message(opponent_id, f"💬 **Raqibingiz:** {message.text}")
                except Exception:
                    pass

@router.callback_query(F.data.startswith("mv:"))
async def cb_move(call: types.CallbackQuery, bot: Bot):
    _, game_id, r, c = call.data.split(":")
    r, c = int(r), int(c)
    g = games.get(game_id)
    if not g or not g['active'] or g['board'][r][c] != ' ':
        return
    
    curr_s = g['symbols'][g['turn_idx']]
    if g['players'][curr_s]['id'] != call.from_user.id:
        return await call.answer("Navbatingiz emas!", show_alert=True)
    
    g['board'][r][c] = g['players'][curr_s]['symbol']
    g['last_move'] = time.time()
    await handle_after_move(bot, game_id)

async def process_robot_turn(bot: Bot, game_id):
    g = games.get(game_id)
    if not g or not g['active']:
        return
    
    curr_s = g['symbols'][g['turn_idx']]
    move = get_robot_move(g['board'], g['size'], MODES[g['mode']]['win_len'], g['players'][curr_s]['symbol'])
    if move:
        r, c = move
        g['board'][r][c] = g['players'][curr_s]['symbol']
        g['last_move'] = time.time()
        await handle_after_move(bot, game_id)
    else:
        await finish_game(bot, game_id)

async def handle_after_move(bot: Bot, game_id):
    g = games.get(game_id)
    if not g or not g['active']:
        return
    
    curr_s = g['symbols'][g['turn_idx']]
    win_symbol = check_winner(g['board'], g['size'], MODES[g['mode']]['win_len'])
    if win_symbol and win_symbol != 'Draw' and curr_s not in g['winners']:
        g['winners'].append(curr_s)
    
    active_p_count = len([s for s in g['symbols'] if s not in g['winners']])
    if is_game_over(g['board'], active_p_count):
        await finish_game(bot, game_id)
        return
    
    next_idx = (g['turn_idx'] + 1) % len(g['symbols'])
    while g['symbols'][next_idx] in g['winners']: 
        next_idx = (next_idx + 1) % len(g['symbols'])
    
    g['turn_idx'] = next_idx
    await update_ui(bot, game_id)
    if g['players'][g['symbols'][next_idx]]['id'] < 0:
        await asyncio.sleep(AI_MOVE_DELAY)
        await process_robot_turn(bot, game_id)

async def finish_game(bot: Bot, game_id, technical_loss_uid=None):
    """O'yinni yakunlash (Texnik mag'lubiyat integratsiyasi bilan)"""
    g = games.get(game_id)
    if not g:
        return
    
    g['active'] = False
    final_markup = get_board_markup(game_id, disabled=True)
    final_ranks = []
    
    # 30 SONIYA TAYMAUT (TEXNIK MAG'LUBIYAT) MANTIIG'I
    if technical_loss_uid:
        lost_player_name = ""
        for s in g['symbols']:
            if g['players'][s]['id'] == technical_loss_uid:
                lost_player_name = g['players'][s]['name']
                final_ranks.append({'user_id': technical_loss_uid, 'rank': 99, 'is_draw': False})
            else:
                # Qolgan barcha o'yinchilar g'olib
                final_ranks.append({'user_id': g['players'][s]['id'], 'rank': 1, 'is_draw': False})
        
        summary_text = f"⌛️ **VAQT TUGADI!**\n\n👤 **{lost_player_name}** 30 soniya ichida yurmagani uchun texnik mag'lubiyat yozildi. Raqib(lar) g'olib! 🏆"
    
    else:
        # ODDIY TUGASH (YURISH ORQALI)
        for i, symbol in enumerate(g['winners'], 1):
            final_ranks.append({'user_id': g['players'][symbol]['id'], 'rank': i, 'is_draw': False})
        
        still_playing = [s for s in g['symbols'] if s not in g['winners']]
        is_true_draw = len(g['winners']) == 0
        for s in still_playing:
            if g['mode'] == 'battle' and len(g['winners']) == 2:
                rank = 3
            else:
                rank = 99
            final_ranks.append({'user_id': g['players'][s]['id'], 'rank': rank, 'is_draw': is_true_draw})

    # Bazaga natijalarni yozish
    results_summary = db.process_game_results(game_id, final_ranks)
    
    if not technical_loss_uid:
        summary_text = f"🏁 **O'YIN YAKUNLANDI!**\n\n🏆 **NATIJALAR:**\n"
        for res in results_summary:
            name = next(g['players'][s]['name'] for s in g['symbols'] if g['players'][s]['id'] == res['user_id'])
            if not res['is_draw'] and res['rank'] <= 2:
                status = f"🥇 {res['rank']}-o'rin"
            elif res['is_draw']:
                status = "🤝 Durrang"
            else:
                status = "❌ Mag'lub"
            summary_text += f"• {name}: {status} — {res['reward']:,} so'm\n"

    # XABARNI YUBORISH (Guruh yoki Lichkaga)
    targets = g['private_chats'] if g.get('is_private') else [(g['group_id'], g['main_msg_id'])]
    for cid, mid in targets:
        try:
            await bot.edit_message_text(chat_id=cid, message_id=mid, text=summary_text, reply_markup=final_markup)
        except Exception:
            pass

    # --- YANGI QISM: FOYDALANUVCHILAGA LICHKADA XABAR YUBORISH ---
    for res in results_summary:
        user_id = res['user_id']
        if user_id < 0:
            continue # Robotlarni o'tkazib yuboramiz

        # Foydalanuvchi profilini olish
        profile = db.get_user_profile(user_id)
        if not profile:
            continue

        # Status va xabarni tayyorlash
        if res['is_draw']:
            status_desc = "🤝 O'yin durrang bilan yakunlandi!"
        elif res['rank'] == 1:
            status_desc = "🏆 G'alaba! Siz o'yinda yutdingiz!"
        else:
            status_desc = "❌ Afsuski, bu safar mag'lub bo'ldingiz."

        active_skin_id = profile.get('active_skin', 'default')
        active_skin_emoji = next((s['symbol'] for s in SHOP_SKINS if s['id'] == active_skin_id), "⬜️")

        private_msg_text = (
            f"🏁 **O'YIN YAKUNLANDI!**\n\n"
            f"{status_desc}\n"
            f"💰 **Sizning mukofotingiz:** {res['reward']:,} so'm\n"
            f"🎭 **Sizning skiningiz:** {active_skin_emoji} ({active_skin_id})\n\n"
            f"🛒 Skin sotib olish uchun /shop buyrug'idan foydalaning.\n"
            f"🎨 Boshqa skin tanlash uchun /skinlar buyrug'idan foydalaning."
        )

        try:
            # Botga start bosgan bo'lsa xabar boradi, bo'lmasa xatolik bermaydi
            await bot.send_message(chat_id=user_id, text=private_msg_text)
        except Exception:
            pass
    # --- YANGI QISM TUGADI ---
            
    if game_id in games:
        del games[game_id]

# --- BO'LIM 5: WATCHDOG (NAZORATCHI) ---

async def game_watchdog(bot: Bot):
    """O'yinlarni nazorat qilish (Taymaut va Robotlar uchun)"""
    while True:
        await asyncio.sleep(3)
        now = time.time()
        active_ids = [gid for gid, g in games.items() if g.get('active') and not gid.startswith('prep_')]
        
        for gid in active_ids:
            g = games.get(gid)
            if not g:
                continue
            
            curr_s = g['symbols'][g['turn_idx']]
            current_player_id = g['players'][curr_s]['id']
            
            # 1. ROBOTLAR UCHUN YURISH (3 SONIYA)
            if current_player_id < 0:
                if (now - g['last_move']) >= 3:
                    try:
                        await process_robot_turn(bot, gid)
                    except Exception:
                        pass
            
            # 2. ODAMLAR UCHUN 30 SONIYA TAYMAUT (TEKSHIRUV)
            else:
                if (now - g['last_move']) >= 30:
                    try:
                        # 30 soniya o'tdi, joriy o'yinchi yutqazdi
                        await finish_game(bot, gid, technical_loss_uid=current_player_id)
                    except Exception as e:
                        logging.error(f"Watchdog timeout error: {e}")