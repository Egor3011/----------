import telebot
from telebot import types

# Укажите ваш токен и ваш Telegram Chat ID (чтобы бот знал, кто админ)
BOT_TOKEN = "8982607403:AAEwC30Jd4LcOWrHZb3JXhspaOirRvmsYH0"
ADMIN_ID = 123456789  # Замените на ваш настоящий ID (можно узнать у @userinfobot)

bot = telebot.TeleBot(BOT_TOKEN)

# Временная база данных (в оперативной памяти)
SERVICES = {
    "Индивидуальная консультация": "3000 руб / 50 мин",
    "Семейная терапия": "4500 руб / 80 мин",
    "Коучинг сессия": "4000 руб / 60 -мин"
}

# Доступные дни и слоты (Админ может менять их через бота)
SCHEDULE = {
    "Понедельник (14.09)": ["10:00", "12:00", "15:00", "17:00"],
    "Вторник (15.09)": ["11:00", "13:00", "16:00"],
    "Среда (16.09)": ["10:00", "14:00", "18:00"]
}

# Хранилище текущих сессий записи клиентов
# Структура: {chat_id: {'service': ..., 'day': ..., 'time': ...}}
user_sessions = {}

# Состояния для админки
admin_state = {}

# --- ГЛАВНОЕ МЕНЮ ---
def get_main_keyboard(chat_id):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_record = types.KeyboardButton("📅 Записаться на сеанс")
    btn_services = types.KeyboardButton("💰 Услуги и цены")
    keyboard.add(btn_record, btn_services)
    
    # Если пишет админ, добавляем кнопку панели управления
    if chat_id == ADMIN_ID:
        btn_admin = types.KeyboardButton("⚙️ Панель Админа")
        keyboard.add(btn_admin)
    return keyboard

@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = "Добро пожаловать! Я бот-помощник психолога.\nЗдесь вы можете ознакомиться с услугами и записаться на сеанс."
    bot.send_message(message.chat.id, welcome_text, reply_markup=get_main_keyboard(message.chat.id))

# --- ЛОГИКА КЛИЕНТА ---

# Просмотр услуг
@bot.message_handler(func=lambda message: message.text == "💰 Услуги и цены")
def show_services(message):
    text = "**Доступные услуги:**\n\n"
    for name, price in SERVICES.items():
        text += f"• {name} — {price}\n"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# Начало записи: Выбор услуги
@bot.message_handler(func=lambda message: message.text == "📅 Записаться на сеанс")
def start_booking(message):
    if not SERVICES:
        bot.send_message(message.chat.id, "К сожалению, список услуг сейчас пуст.")
        return
        
    keyboard = types.InlineKeyboardMarkup()
    for service in SERVICES.keys():
        keyboard.add(types.InlineKeyboardButton(text=service, callback_data=f"select_srv:{service}"))
    
    bot.send_message(message.chat.id, "Выберите подходящую услугу:", reply_markup=keyboard)

# Выбор дня
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_srv:"))
def process_service_choice(call):
    service_name = call.data.split(":")[1]
    user_sessions[call.message.chat.id] = {"service": service_name}
    
    if not SCHEDULE:
        bot.send_message(call.message.chat.id, "На ближайшие дни нет доступного времени для записи.")
        return

    keyboard = types.InlineKeyboardMarkup()
    for day in SCHEDULE.keys():
        # Показываем только дни, где есть свободные слоты
        if SCHEDULE[day]:
            keyboard.add(types.InlineKeyboardButton(text=day, callback_data=f"select_day:{day}"))
            
    bot.edit_message_text("Отлично. Теперь выберите удобный день:", 
                          chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          reply_markup=keyboard)

# Выбор времени
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_day:"))
def process_day_choice(call):
    day_name = call.data.split(":")[1]
    if call.message.chat.id in user_sessions:
        user_sessions[call.message.chat.id]["day"] = day_name
    
    keyboard = types.InlineKeyboardMarkup()
    # Создаем кнопки со временем
    for time_slot in SCHEDULE[day_name]:
        keyboard.add(types.InlineKeyboardButton(text=time_slot, callback_data=f"select_time:{time_slot}"))
        
    bot.edit_message_text(f"Вы выбрали {day_name}. Выберите время сеанса:", 
                          chat_id=call.message.chat.id, 
                          message_id=call.message.message_id, 
                          reply_markup=keyboard)

# Подтверждение записи
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_time:"))
def process_time_choice(call):
    time_slot = call.data.split(":")[1]
    chat_id = call.message.chat.id
    
    if chat_id not in user_sessions:
        bot.send_message(chat_id, "Ошибка сессии. Начните запись сначала.")
        return
        
    user_sessions[chat_id]["time"] = time_slot
    session = user_sessions[chat_id]
    
    # Удаляем выбранный слот из графика, чтобы никто больше не записался
    if session["day"] in SCHEDULE and time_slot in SCHEDULE[session["day"]]:
        SCHEDULE[session["day"]].remove(time_slot)
    
    # Формируем сообщение клиенту
    success_text = (f"🎉 **Вы успешно записаны!**\n\n"
                    f"🔹 **Услуга:** {session['service']}\n"
                    f"📅 **Дата:** {session['day']}\n"
                    f"🕒 **Время:** {session['time']}\n\n"
                    f"Психолог свяжется с вами в ближайшее время.")
    
    bot.edit_message_text(success_text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown")
    
    # Уведомление психологу (админу)
    client_info = f"@{call.from_user.username}" if call.from_user.username else f"ID: {chat_id}"
    admin_text = (f"🔔 **Новая запись!**\n\n"
                  f"👤 **Клиент:** {call.from_user.first_name} ({client_info})\n"
                  f"🔹 **Услуга:** {session['service']}\n"
                  f"📅 **День:** {session['day']}\n"
                  f"🕒 **Время:** {session['time']}")
    
    bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown")
    # Очищаем сессию клиента
    del user_sessions[chat_id]


# --- ЛОГИКА АДМИНИСТРАТОРА (ПСИХОЛОГА) ---

@bot.message_handler(func=lambda message: message.text == "⚙️ Панель Админа" and message.chat.id == ADMIN_ID)
def admin_panel(message):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("➕ Добавить день/время", callback_data="adm_add_sched"))
    keyboard.add(types.InlineKeyboardButton("🧹 Очистить весь график", callback_data="adm_clear_sched"))
    keyboard.add(types.InlineKeyboardButton("➕ Добавить услугу", callback_data="adm_add_srv"))
    
    bot.send_message(ADMIN_ID, "Управление расписанием и услугами:", reply_markup=keyboard)

# Очистка графика
@bot.callback_query_handler(func=lambda call: call.data == "adm_clear_sched" and call.message.chat.id == ADMIN_ID)
def admin_clear_schedule(call):
    SCHEDULE.clear()
    bot.answer_callback_query(call.id, "График полностью очищен!")
    bot.edit_message_text("График пуст. Клиенты не смогут записаться, пока вы не добавите новые слоты.", 
                          chat_id=ADMIN_ID, message_id=call.message.message_id)

# Добавление времени (Шаг 1: Запрос текста)
@bot.callback_query_handler(func=lambda call: call.data == "adm_add_sched" and call.message.chat.id == ADMIN_ID)
def admin_add_schedule_prompt(call):
    text = ("Введите новый день и слоты в формате:\n"
            "`День (Дата) - Время1, Время2, Время3`\n\n"
            "Пример:\n"
            "`Четверг (17.09) - 12:00, 14:00, 16:30`")
    bot.edit_message_text(text, chat_id=ADMIN_ID, message_id=call.message.message_id, parse_mode="Markdown")
    admin_state[ADMIN_ID] = "waiting_for_schedule"

# Добавление услуги (Шаг 1: Запрос текста)
@bot.callback_query_handler(func=lambda call: call.data == "adm_add_srv" and call.message.chat.id == ADMIN_ID)
def admin_add_service_prompt(call):
    text = ("Введите новую услугу и цену в формате:\n"
            "`Название услуги - Цена и длительность`\n\n"
            "Пример:\n"
            "`Онлайн консультация - 2500 руб / 60 мин`")
    bot.edit_message_text(text, chat_id=ADMIN_ID, message_id=call.message.message_id, parse_mode="Markdown")
    admin_state[ADMIN_ID] = "waiting_for_service"

# Обработчик текстовых ответов от Админа (ввод данных)
@bot.message_handler(func=lambda message: message.chat.id == ADMIN_ID and admin_state.get(ADMIN_ID) is not None)
def handle_admin_input(message):
    state = admin_state.get(ADMIN_ID)
    
    if state == "waiting_for_schedule":
        try:
            # Разделяем день и время по знаку "-"
            day, times_str = message.text.split("-")
            day = day.strip()
            # Разделяем слоты времени по запятой
            times = [t.strip() for t in times_str.split(",")]
            
            if day in SCHEDULE:
                SCHEDULE[day].extend(times) # Если день есть, добавляем время
            else:
                SCHEDULE[day] = times # Если дня нет, создаем новый
                
            bot.send_message(ADMIN_ID, f"✅ График успешно обновлен для дня: {day}", reply_markup=get_main_keyboard(ADMIN_ID))
        except Exception:
            bot.send_message(ADMIN_ID, "❌ Ошибка формата. Попробуйте еще раз по примеру:\n`Пятница - 10:00, 11:00`", parse_mode="Markdown")
            
    elif state == "waiting_for_service":
        try:
            name, price = message.text.split("-")
            SERVICES[name.strip()] = price.strip()
            bot.send_message(ADMIN_ID, f"✅ Услуга '{name.strip()}' успешно добавлена!", reply_markup=get_main_keyboard(ADMIN_ID))
        except Exception:
            bot.send_message(ADMIN_ID, "❌ Ошибка формата. Попробуйте еще раз по примеру:\n`Консультация - 2000 руб`", parse_mode="Markdown")

    # Сбрасываем состояние админа
    admin_state[ADMIN_ID] = None

# Запуск бота
if __name__ == '__main__':
    print("Бот успешно запущен...")
    bot.infinity_polling()
