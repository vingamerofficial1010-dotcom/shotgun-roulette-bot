import telebot
from telebot import types
import random
import os
from flask import Flask
import threading

# --- КОНФИГУРАЦИЯ ---
TOKEN = '8725622605:AAGz43AVk0jyjDtZ9t4qP2FQWFPPBQark0Y' # Замени на свой токен от @BotFather
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Глобальное состояние игры
game = {
    "is_active": False,
    "status": "waiting",
    "chat_id": None,
    "players": {},
    "turn_order": [],
    "current_index": 0,
    "cartridges": []
}

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER (чтобы не засыпал) ---
@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# --- ЛОГИКА ИГРЫ ---

@bot.message_handler(func=lambda message: message.text.lower() == 'начать регистрацию')
def start_reg(message):
    if game["is_active"]:
        bot.send_message(message.chat.id, "❌ Игра уже запущена!")
        return
    
    game.update({"is_active": True, "status": "waiting", "players": {}, "chat_id": message.chat.id})
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Присоединиться 🔫", callback_data="join"))
    bot.send_message(message.chat.id, "📢 <b>Набор в Русскую Рулетку!</b>\nНужно минимум 2 игрока.\nНапишите 'старт игры', когда все соберутся.", 
                     parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "join")
def join(call):
    if game["status"] != "waiting":
        return bot.answer_callback_query(call.id, "Слишком поздно!")
    
    uid = call.from_user.id
    if uid in game["players"]:
        return bot.answer_callback_query(call.id, "Ты уже в списке!")

    name = f"{call.from_user.first_name} (@{call.from_user.username})" if call.from_user.username else call.from_user.first_name
    game["players"][uid] = {"name": name, "lives": 4}
    
    bot.answer_callback_query(call.id, "Ты в игре!")
    bot.edit_message_text(f"📢 <b>Набор в игру</b>\nУчастников: {len(game['players'])}", 
                          call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=call.message.reply_markup)

@bot.message_handler(func=lambda message: message.text.lower() == 'старт игры')
def start_game(message):
    if not game["is_active"] or len(game["players"]) < 2:
        return bot.send_message(message.chat.id, "Нужно хотя бы 2 игрока!")
    
    game["status"] = "playing"
    game["turn_order"] = list(game["players"].keys())
    random.shuffle(game["turn_order"])
    bot.send_message(message.chat.id, "🔥 <b>ИГРА НАЧИНАЕТСЯ!</b>\nУ каждого по 4 ❤️", parse_mode="HTML")
    new_round()

def new_round():
    total = random.randint(2, 6)
    loaded = random.randint(1, total - 1)
    game["cartridges"] = [True] * loaded + [False] * (total - loaded)
    random.shuffle(game["cartridges"])
    
    status_text = "\n".join([f"👤 {p['name']}: {'❤️' * p['lives']}" for p in game["players"].values()])
    bot.send_message(game["chat_id"], f"🎰 <b>Новый раунд!</b>\nЗаряжено: {loaded} | Пусто: {total-loaded}\n\n{status_text}", parse_mode="HTML")
    ask_action()

def ask_action():
    if len(game["turn_order"]) <= 1:
        winner = game["players"][game["turn_order"][0]]['name']
        bot.send_message(game["chat_id"], f"🏆 <b>ПОБЕДИТЕЛЬ: {winner}</b>", parse_mode="HTML")
        game["is_active"] = False
        return

    if not game["cartridges"]:
        bot.send_message(game["chat_id"], "🔂 Патроны кончились. Перезарядка...")
        return new_round()

    curr_id = game["turn_order"][game["current_index"]]
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("В себя", callback_data="s_self"), 
               types.InlineKeyboardButton("В другого", callback_data="s_other"))
    
    bot.send_message(game["chat_id"], f"👉 Ход игрока <b>{game['players'][curr_id]['name']}</b>\nПрими решение:", 
                     parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["s_self", "s_other"])
def shot_choice(call):
    curr_id = game["turn_order"][game["current_index"]]
    if call.from_user.id != curr_id:
        return bot.answer_callback_query(call.id, "Не твой ход!")

    bot.delete_message(call.message.chat.id, call.message.message_id)
    
    if call.data == "s_self":
        do_shot(curr_id, curr_id)
    else:
        markup = types.InlineKeyboardMarkup()
        for pid in game["turn_order"]:
            if pid != curr_id:
                markup.add(types.InlineKeyboardButton(game["players"][pid]["name"], callback_data=f"t_{pid}"))
        bot.send_message(game["chat_id"], "Выбери цель:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("t_"))
def target_choice(call):
    curr_id = game["turn_order"][game["current_index"]]
    if call.from_user.id != curr_id: return
    
    target_id = int(call.data.replace("t_", ""))
    bot.delete_message(call.message.chat.id, call.message.message_id)
    do_shot(curr_id, target_id)

def do_shot(sh_id, t_id):
    hit = game["cartridges"].pop(0)
    sh_name = game["players"][sh_id]["name"]
    t_name = game["players"][t_id]["name"]
    
    if hit:
        game["players"][t_id]["lives"] -= 1
        res = f"💥 <b>БАБАХ!</b> {t_name} ранен!"
        if game["players"][t_id]["lives"] <= 0:
            res += f"\n💀 {t_name} выбывает!"
            game["turn_order"].remove(t_id)
            if sh_id == t_id or game["turn_order"].index(sh_id) >= len(game["turn_order"]):
                game["current_index"] -= 1
    else:
        res = f"🍃 <i>Щелк...</i> Холостой! {t_name} в порядке."

    bot.send_message(game["chat_id"], f"🔫 {sh_name} стреляет в {t_name}...\n\n{res}", parse_mode="HTML")
    game["current_index"] = (game["current_index"] + 1) % len(game["turn_order"])
    ask_action()

# --- ЗАПУСК ---
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.infinity_polling()
