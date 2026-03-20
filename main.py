import telebot
from telebot import types
import random
import threading
import time
from flask import Flask

# --- НАСТРОЙКИ ---
TOKEN = '8725622605:AAGz43AVk0jyjDtZ9t4qP2FQWFPPBQark0Y'  # ЗАМЕНИ НА СВОЙ ТОКЕН!
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- ГЛОБАЛЬНОЕ СОСТОЯНИЕ ИГРЫ ---
game = {
    "is_active": False,
    "status": "waiting",
    "chat_id": None,
    "players": {},
    "turn_order": [],
    "current_index": 0,
    "cartridges": [],
    "turn_id": 0  # Уникальный ID хода для проверки таймера
}

# --- СИСТЕМА ТАЙМ-АУТА (2 МИНУТЫ) ---
def start_timer(chat_id, turn_id):
    time.sleep(120)  # Ждем 120 секунд
    # Проверяем, что игра всё еще идет и этот ход всё еще актуален
    if game["is_active"] and game["status"] == "playing" and game["turn_id"] == turn_id:
        curr_id = game["turn_order"][game["current_index"]]
        player_name = game["players"][curr_id]["name"]
        
        bot.send_message(chat_id, f"⏰ <b>{player_name}</b> слишком долго думал! Ход переходит к следующему.", parse_mode="HTML")
        
        # Передаем ход следующему
        game["current_index"] = (game["current_index"] + 1) % len(game["turn_order"])
        ask_action()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def ask_action():
    if not game["is_active"] or not game["turn_order"]:
        return
    
    curr_id = game["turn_order"][game["current_index"]]
    game["turn_id"] += 1  # Обновляем ID хода для нового таймера
    
    # Запускаем таймер в фоновом потоке
    threading.Thread(target=start_timer, args=(game["chat_id"], game["turn_id"])).start()
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💥 Выстрелить в себя", callback_data="shoot_self"))
    markup.add(types.InlineKeyboardButton("🔫 Выстрелить в противника", callback_data="shoot_enemy"))
    
    bot.send_message(game["chat_id"], 
                     f"👉 Ход игрока: <b>{game['players'][curr_id]['name']}</b>\n"
                     f"❤️ Твои HP: {game['players'][curr_id]['hp']}\n"
                     f"У тебя есть 2 минуты!", 
                     parse_mode="HTML", reply_markup=markup)

# --- ОБРАБОТЧИКИ КОМАНД ---
@bot.message_handler(commands=['reset_game'])
def reset_game_handler(message):
    global game
    game.update({
        "is_active": False, "status": "waiting", "players": {}, 
        "turn_order": [], "current_index": 0, "cartridges": [], "turn_id": 0
    })
    bot.send_message(message.chat.id, "♻️ <b>Игра принудительно сброшена!</b> Можно начинать новую.", parse_mode="HTML")

@bot.message_handler(commands=['start_roulette'])
def start_reg(message):
    if game["is_active"]:
        bot.reply_to(message, "❌ Игра уже запущена! Используй /reset_game, если она зависла.")
        return
    
    game.update({
        "is_active": True, "status": "waiting", "chat_id": message.chat.id,
        "players": {}, "turn_order": [], "current_index": 0, "turn_id": 0
    })
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Участвовать", callback_data="join_game"))
    markup.add(types.InlineKeyboardButton("Начать бой", callback_data="start_battle"))
    
    bot.send_message(message.chat.id, "🎯 <b>Регистрация в Shotgun Roulette!</b>\nНажимайте кнопку ниже:", 
                     parse_mode="HTML", reply_markup=markup)

# --- ОБРАБОТКА CALLBACK (КНОПКИ) ---
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    global game
    user_id = call.from_user.id

    # РЕГИСТРАЦИЯ
    if call.data == "join_game":
        if user_id not in game["players"]:
            game["players"][user_id] = {"name": call.from_user.first_name, "hp": 3}
            bot.answer_callback_query(call.id, "Ты в игре!")
        else:
            bot.answer_callback_query(call.id, "Ты уже в списке.")

    # ЗАПУСК БОЯ
    elif call.data == "start_battle":
        if len(game["players"]) < 2:
            bot.answer_callback_query(call.id, "Нужно минимум 2 игрока!", show_alert=True)
            return
        
        game["status"] = "playing"
        game["turn_order"] = list(game["players"].keys())
        random.shuffle(game["turn_order"])
        game["cartridges"] = [True, False, False, True, False] # 2 боевых, 3 холостых
        random.shuffle(game["cartridges"])
        
        bot.send_message(game["chat_id"], "🎞 Барабан прокручен! В нем 2 боевых и 3 холостых.")
        ask_action()

    # ЛОГИКА СТРЕЛЬБЫ
    elif call.data in ["shoot_self", "shoot_enemy"]:
        curr_id = game["turn_order"][game["current_index"]]
        if user_id != curr_id:
            bot.answer_callback_query(call.id, "❌ Сейчас не твой ход!", show_alert=True)
            return

        # Проверка наличия патронов
        if not game["cartridges"]:
            game["cartridges"] = [True, False, False, True, False]
            random.shuffle(game["cartridges"])
            bot.send_message(game["chat_id"], "🔄 Патроны закончились. Перезарядка!")

        is_live = game["cartridges"].pop(0)
        game["turn_id"] += 1 # Сбрасываем старый таймер
        
        target_id = user_id if call.data == "shoot_self" else next(p for p in game["turn_order"] if p != user_id)

        if is_live:
            game["players"][target_id]["hp"] -= 1
            bot.send_message(game["chat_id"], f"💥 <b>БАБАХ!</b> Патрон боевой. {game['players'][target_id]['name']} теряет 1 HP.", parse_mode="HTML")
            
            if game["players"][target_id]["hp"] <= 0:
                bot.send_message(game["chat_id"], f"💀 <b>{game['players'][target_id]['name']}</b> выбывает!")
                game["turn_order"].remove(target_id)
                if len(game["turn_order"]) == 1:
                    winner = game["players"][game["turn_order"][0]]["name"]
                    bot.send_message(game["chat_id"], f"🏆 <b>ИГРА ОКОНЧЕНА! Победитель: {winner}</b>", parse_mode="HTML")
                    game["is_active"] = False
                    return
        else:
            bot.send_message(game["chat_id"], "🖱 <b>ЩЕЛЧОК...</b> Холостой!", parse_mode="HTML")
            if call.data == "shoot_self":
                bot.send_message(game["chat_id"], "🎲 Риск оправдан! Стрелял в себя холостым — ходишь снова.")
                ask_action()
                return

        # Переход хода
        game["current_index"] = (game["current_index"] + 1) % len(game["turn_order"])
        ask_action()

# --- FLASK ДЛЯ RENDER (НЕ УДАЛЯТЬ) ---
@app.route('/')
def index():
    return "I'm alive!"

def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.polling(none_stop=True)
