import telebot
from telebot import types
import random
import threading
import time
from flask import Flask

# --- НАСТРОЙКИ ---
TOKEN = '8725622605:AAGz43AVk0jyjDtZ9t4qP2FQWFPPBQark0Y' 
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- ДАННЫЕ ИГРЫ ---
ITEMS = {
    "cig": "🚬 Сигарета",
    "knife": "🔪 Нож",
    "drink": "🧃 Напиток",
    "glass": "🔍 Лупа"
}

# Словарь для хранения игр во всех чатах: {chat_id: game_data}
games = {}

def get_game(chat_id):
    """Инициализация или получение данных игры для конкретного чата"""
    if chat_id not in games:
        games[chat_id] = {
            "is_active": False,
            "status": "waiting_mode",
            "mode": "normal",
            "players": {},
            "turn_order": [],
            "current_index": 0,
            "cartridges": [],
            "turn_id": 0,
            "reg_msg_id": None
        }
    return games[chat_id]

# --- ЛОГИКА ИГРЫ ---

def reload_gun(chat_id):
    g = get_game(chat_id)
    # 2 боевых, 3 холостых
    g["cartridges"] = [True, True, False, False, False]
    random.shuffle(g["cartridges"])
    
    live = sum(g["cartridges"])
    blank = len(g["cartridges"]) - live
    
    bot.send_message(chat_id, f"🔄 <b>ЗАРЯЖАЕМ ДРОБОВИК...</b>\n🔴 Боевых: {live} | ⚪️ Холостых: {blank}", parse_mode="HTML")
    
    if g["mode"] == "items":
        for p_id in g["players"]:
            # Выдача 2 предметов, максимум 8 в инвентаре
            new_items = [random.choice(list(ITEMS.keys())) for _ in range(2)]
            g["players"][p_id]["items"].extend(new_items)
            g["players"][p_id]["items"] = g["players"][p_id]["items"][:8]
        bot.send_message(chat_id, "🎒 <b>Раунд начался!</b> Всем выдано по 2 предмета.")

def update_reg_text(chat_id):
    g = get_game(chat_id)
    mode_text = "С ПРЕДМЕТАМИ 🎒" if g["mode"] == "items" else "ОБЫЧНЫЙ 🔫"
    text = f"🎯 <b>Регистрация в Shotgun Roulette!</b>\nРежим: <b>{mode_text}</b>\n\n👥 <b>Участники:</b>\n"
    if not g["players"]:
        text += "<i>Ожидание игроков...</i>"
    else:
        for p in g["players"].values():
            text += f"— {p['name']}\n"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Вступить", callback_data="join"))
    if len(g["players"]) >= 2:
        markup.add(types.InlineKeyboardButton("Начать бой 🧨", callback_data="start_fight"))
    return text, markup

def start_timer(chat_id, turn_id):
    time.sleep(120)
    g = get_game(chat_id)
    if g["is_active"] and g["turn_id"] == turn_id:
        curr_id = g["turn_order"][g["current_index"]]
        bot.send_message(chat_id, f"⏰ <b>{g['players'][curr_id]['name']}</b> уснул. Ход переходит к следующему!")
        next_turn(chat_id)

def ask_action(chat_id):
    g = get_game(chat_id)
    if not g["is_active"] or not g["turn_order"]: return
    
    curr_id = g["turn_order"][g["current_index"]]
    g["turn_id"] += 1
    threading.Thread(target=start_timer, args=(chat_id, g["turn_id"])).start()
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💥 В себя", callback_data="shoot_self"),
               types.InlineKeyboardButton("🔫 В противника", callback_data="choose_target"))
    
    if g["mode"] == "items" and g["players"][curr_id]["items"]:
        markup.add(types.InlineKeyboardButton("🎒 Инвентарь", callback_data="open_inv"))

    p = g["players"][curr_id]
    bot.send_message(chat_id, f"👉 Ход: <b>{p['name']}</b>\n❤️ HP: {p['hp']}\nУ тебя 2 минуты!", 
                     parse_mode="HTML", reply_markup=markup)

def next_turn(chat_id):
    g = get_game(chat_id)
    g["current_index"] = (g["current_index"] + 1) % len(g["turn_order"])
    if not g["cartridges"]: reload_gun(chat_id)
    ask_action(chat_id)

# --- ОБРАБОТЧИКИ КОМАНД ---

@bot.message_handler(commands=['reset_game'])
def reset(message):
    cid = message.chat.id
    games[cid] = {
        "is_active": False, "status": "waiting_mode", "players": {}, 
        "turn_order": [], "cartridges": [], "turn_id": 0
    }
    bot.send_message(cid, "♻️ <b>Игра в этом чате сброшена!</b>", parse_mode="HTML")

@bot.message_handler(commands=['start_roulette'])
def start(message):
    cid = message.chat.id
    g = get_game(cid)
    if g["is_active"]:
        bot.reply_to(message, "❌ Тут уже играют. Напиши /reset_game для сброса.")
        return
    
    g.update({"is_active": True, "status": "waiting_mode", "players": {}})
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Без предметов", callback_data="set_normal"),
               types.InlineKeyboardButton("С предметами", callback_data="set_items"))
    bot.send_message(cid, "⚙️ <b>Выберите тип игры:</b>", parse_mode="HTML", reply_markup=markup)

# --- ОБРАБОТКА КНОПОК ---

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    cid = call.message.chat.id
    uid = call.from_user.id
    g = get_game(cid)

    # 1. Режимы и Регистрация
    if call.data.startswith("set_"):
        g["mode"] = "items" if call.data == "set_items" else "normal"
        g["status"] = "reg"
        text, m = update_reg_text(cid)
        msg = bot.send_message(cid, text, parse_mode="HTML", reply_markup=m)
        g["reg_msg_id"] = msg.message_id

    elif call.data == "join":
        if uid not in g["players"]:
            g["players"][uid] = {"name": call.from_user.first_name, "hp": 3, "items": [], "dmg_boost": False}
            text, m = update_reg_text(cid)
            bot.edit_message_text(text, cid, g["reg_msg_id"], reply_markup=m, parse_mode="HTML")
        bot.answer_callback_query(call.id)

    elif call.data == "start_fight":
        if len(g["players"]) < 2: return
        g["status"] = "playing"
        g["turn_order"] = list(g["players"].keys())
        random.shuffle(g["turn_order"])
        bot.delete_message(cid, g["reg_msg_id"])
        reload_gun(cid)
        ask_action(cid)

    # 2. Игровые действия (проверка хода)
    else:
        if not g["is_active"]: return
        curr_id = g["turn_order"][g["current_index"]]
        
        # Разрешаем просмотр инвентаря/целей только в свой ход
        if uid != curr_id and not call.data.startswith("fire_at_"):
            bot.answer_callback_query(call.id, "❌ Сейчас не твой ход!", show_alert=True)
            return

        # В СЕБЯ
        if call.data == "shoot_self":
            bot.delete_message(cid, call.message.message_id)
            execute_shot(cid, uid, uid)

        # ВЫБОР ЦЕЛИ
        elif call.data == "choose_target":
            m = types.InlineKeyboardMarkup()
            for p_id in g["turn_order"]:
                if p_id != uid:
                    m.add(types.InlineKeyboardButton(f"🎯 {g['players'][p_id]['name']}", callback_data=f"fire_at_{p_id}"))
            m.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu"))
            bot.edit_message_reply_markup(cid, call.message.message_id, reply_markup=m)

        elif call.data.startswith("fire_at_"):
            target = int(call.data.split("_")[2])
            bot.delete_message(cid, call.message.message_id)
            execute_shot(cid, uid, target)

        # ИНВЕНТАРЬ
        elif call.data == "open_inv":
            m = types.InlineKeyboardMarkup()
            for i, it in enumerate(g["players"][uid]["items"]):
                m.add(types.InlineKeyboardButton(ITEMS[it], callback_data=f"use_{i}"))
            m.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu"))
            bot.edit_message_reply_markup(cid, call.message.message_id, reply_markup=m)

        elif call.data.startswith("use_"):
            idx = int(call.data.split("_")[1])
            p = g["players"][uid]
            item = p["items"].pop(idx)
            bot.delete_message(cid, call.message.message_id)
            bot.send_message(cid, f"🎒 <b>{p['name']}</b> использует: {ITEMS[item]}", parse_mode="HTML")
            
            if item == "cig":
                p["hp"] += 1
            elif item == "knife":
                p["dmg_boost"] = True
            elif item == "drink":
                if not g["cartridges"]: reload_gun(cid)
                out = g["cartridges"].pop(0)
                txt = "🔴 Боевой" if out else "⚪️ Холостой"
                bot.send_message(cid, f"🧃 Из ствола вылетел патрон: {txt}")
            elif item == "glass":
                if not g["cartridges"]: reload_gun(cid)
                txt = "🔴 БОЕВОЙ" if g["cartridges"][0] else "⚪️ ХОЛОСТОЙ"
                bot.answer_callback_query(call.id, f"🔍 Ты видишь: патрон {txt}", show_alert=True)
            
            ask_action(cid)

        elif call.data == "back_to_menu":
            bot.delete_message(cid, call.message.message_id)
            ask_action(cid)

def execute_shot(chat_id, shooter_id, target_id):
    g = get_game(chat_id)
    if not g["cartridges"]: reload_gun(chat_id)
    
    is_live = g["cartridges"].pop(0)
    g["turn_id"] += 1
    
    damage = 2 if g["players"][shooter_id]["dmg_boost"] else 1
    g["players"][shooter_id]["dmg_boost"] = False
    
    if is_live:
        g["players"][target_id]["hp"] -= damage
        bot.send_message(chat_id, f"💥 <b>БА-БАХ!</b> {g['players'][target_id]['name']} получает {damage} урона!", parse_mode="HTML")
        if g["players"][target_id]["hp"] <= 0:
            bot.send_message(chat_id, f"💀 <b>{g['players'][target_id]['name']}</b> выбыл!")
            g["turn_order"].remove(target_id)
            if len(g["turn_order"]) <= 1:
                w = g["players"][g["turn_order"][0]]["name"]
                bot.send_message(chat_id, f"🏆 <b>ИГРА ОКОНЧЕНА! Победитель: {w}</b>", parse_mode="HTML")
                g["is_active"] = False
                return
    else:
        bot.send_message(chat_id, "🖱 <b>Щелчок...</b> Холостой!")
        if shooter_id == target_id:
            bot.send_message(chat_id, "🎲 Ты рискнул и выжил! Ходи еще раз.")
            ask_action(chat_id)
            return
            
    next_turn(chat_id)

# --- FLASK (ДЛЯ RENDER) ---
@app.route('/')
def h(): return "Bot Multi-Chat Alive"

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5000)).start()
    bot.polling(none_stop=True)
