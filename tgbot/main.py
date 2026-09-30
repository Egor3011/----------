"""Telegram booking bot. Run with: python tgbot/main.py."""
import logging
import re
from datetime import date
from html import escape
from threading import Event, Thread

import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException

from config import Config
from storage import BookingError, Store

LOG = logging.getLogger(__name__)
WEEKDAYS = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")
STATUSES = {"pending": "⏳ Ожидает решения", "confirmed": "✅ Подтверждена", "cancelled": "❌ Отменена"}
WELCOME = (
    "🌿 <b>Добро пожаловать!</b>\n\n"
    "Иногда, чтобы лучше понять себя, достаточно остановиться, выдохнуть и поговорить.\n\n"
    "Я помогу подобрать подходящий формат встречи и удобное время.\n\n"
    "🎁 Для первой записи действует <b>скидка 50%</b>."
)
DETAILS = (
    "ℹ️ <b>Подробности</b>\n\nИндивидуальная встреча длится 60 минут.\n\n"
    "После отправки заявки менеджер свяжется с вами и подтвердит дату и время.\n\n"
    "Если подходящего времени нет, можно оставить запрос менеджеру — "
    "мы постараемся подобрать удобный вариант."
)
PRICES = (
    "💰 <b>Цены</b>\n\n"
    "• 1 встреча — <b>2 500 ₽</b>.\n"
    "• Пакет 5 встреч — <b>2 000 ₽ за встречу</b>, всего 10 000 ₽.\n"
    "• Пакет 10 встреч — <b>1 500 ₽ за встречу</b>, всего 15 000 ₽.\n"
    "• Пакет 10 встреч — <b>900 ₽ за встречу</b>, всего 9 000 ₽.\n\n"
    "🎁 Для первой записи действует скидка 50%.\n"
    "Чтобы уточнить условия пакетов и купить, напишите администратору: @h010dok."
)


def day_label(day):
    value = date.fromisoformat(day)
    return f"{value:%d.%m.%Y}, {WEEKDAYS[value.weekday()]}"


def interval(hour):
    return f"{hour:02d}:00–{hour + 1:02d}:00"


def button(text, data=None, url=None):
    return types.InlineKeyboardButton(text, callback_data=data, url=url)


def keyboard(rows):
    result = types.InlineKeyboardMarkup()
    for row in rows:
        result.row(*row)
    return result


def back(data="home"):
    return [button("⬅️ Назад", data)]


class BookingBot:
    def __init__(self, bot, store, config):
        self.bot = bot
        self.store = store
        self.config = config
        self.sessions = {}
        self.panels = {}
        bot.register_message_handler(self.on_message, content_types=["text", "contact"])
        bot.register_callback_query_handler(self.on_callback, func=lambda call: True)

    def manager_button(self):
        return [button("✉️ Написать менеджеру", url=f"https://t.me/{self.config.manager}")]

    def screen(self, chat_id, text, rows, fresh=False):
        markup = keyboard(rows)
        message_id = self.panels.get(chat_id)
        if message_id and not fresh:
            try:
                self.bot.edit_message_text(text, chat_id, message_id,
                                           reply_markup=markup, parse_mode="HTML")
                return
            except ApiTelegramException as exc:
                if "message is not modified" in exc.description.lower():
                    return
                if exc.error_code != 400:
                    raise
                # Telegram may no longer allow editing an old/deleted message.
        message = self.bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
        self.panels[chat_id] = message.message_id

    def home(self, chat_id, fresh=False):
        self.sessions.pop(chat_id, None)
        rows = [[button("📅 Записаться", "book")],
                [button("ℹ️ Подробнее", "details"), button("💬 Отзывы", "reviews")],
                [button("💰 Цены", "prices")]]
        if chat_id == self.config.admin_id:
            rows.append([button("⚙️ Админ-панель", "adm:home")])
        self.screen(chat_id, WELCOME, rows, fresh)

    def show_days(self, chat_id):
        session = self.sessions.setdefault(chat_id, {})
        session["step"] = "day"
        rows = [[button(day_label(day), f"day:{day}")] for day in self.store.days()
                if self.store.available_hours(day)]
        text = ("📅 <b>Выберите дату</b>\n\nЗапись доступна на две недели вперёд.\n"
                "Пн–сб, 08:00–18:00. Воскресенье — выходной.\n"
                f"Часовой пояс: {escape(self.config.timezone)}.\n\n"
                "Своё время можно согласовать отдельно с менеджером, с доплатой.")
        if not rows:
            text += "\n\nСвободных дат пока нет. Напишите менеджеру."
        self.screen(chat_id, text, rows + [self.manager_button(), back()])

    def show_times(self, chat_id):
        session = self.sessions[chat_id]
        session["step"] = "time"
        hours = self.store.available_hours(session["day"])
        options = [button(f"{hour:02d}:00", f"hour:{hour}") for hour in hours]
        rows = [options[i:i + 3] for i in range(0, len(options), 3)]
        text = (f"📅 <b>{day_label(session['day'])}</b>\n\n"
                "Выберите время начала. Встреча длится 60 минут.\n"
                f"Часовой пояс: {escape(self.config.timezone)}.")
        if not hours:
            text += "\n\nСвободного времени на эту дату уже нет. Выберите другую дату."
        self.screen(chat_id, text, rows + [self.manager_button(), back("booking:back")])

    def comment_prompt(self, chat_id):
        self.sessions[chat_id]["step"] = "comment"
        self.screen(chat_id, "💬 <b>Комментарий к записи</b>\n\n"
                    "Напишите сообщение для специалиста (до 1000 символов) или пропустите этот шаг.",
                    [[button("Пропустить", "skip:comment")], back("booking:back")])

    def phone_prompt(self, chat_id):
        self.sessions[chat_id]["step"] = "phone"
        self.screen(chat_id, "📱 <b>Номер телефона — по желанию</b>\n\n"
                    "Введите номер с кодом страны, например +7 999 123-45-67, "
                    "отправьте свой контакт через меню вложений или пропустите шаг.",
                    [[button("Пропустить", "skip:phone")], back("booking:back")])

    def review(self, chat_id):
        session = self.sessions[chat_id]
        session["step"] = "review"
        self.screen(chat_id,
                    "📝 <b>Проверьте заявку</b>\n\n"
                    f"📅 {day_label(session['day'])}\n🕒 {interval(session['hour'])}\n"
                    f"Часовой пояс: {escape(self.config.timezone)}.\n"
                    f"📱 Телефон: {escape(session.get('phone') or 'не указан')}\n"
                    f"💬 Комментарий: {escape(session.get('comment') or 'не указан')}\n\n"
                    "После отправки заявки дождитесь подтверждения администратора.",
                    [[button("✅ Записаться", "submit")], back("booking:back")])

    def admin_home(self, chat_id):
        self.sessions.pop(chat_id, None)
        self.screen(chat_id, "⚙️ <b>Админ-панель</b>\n\n"
                    "Заявки и подтверждённые встречи занимают время в расписании.\n"
                    "Перерывы исключают выбранные часы из записи.",
                    [[button("📋 Предстоящие записи и заявки", "adm:list:0")],
                     [button("☕ Добавить перерыв", "adm:breakdays")],
                     [button("🗓 Мои перерывы", "adm:breaklist:0")], back()])

    def booking_text(self, row):
        username = f"@{escape(row['username'])}" if row["username"] else "без username"
        return (f"<b>Запись №{row['id']}</b> — {STATUSES[row['status']]}\n\n"
                f"👤 <a href=\"tg://user?id={row['user_id']}\">{escape(row['name'])}</a> "
                f"({username}, ID: {row['user_id']})\n"
                f"📅 {day_label(row['day'])}\n🕒 {interval(row['hour'])}\n"
                f"Часовой пояс: {escape(self.config.timezone)}.\n"
                f"📱 {escape(row['phone'] or 'Телефон не указан')}\n"
                f"💬 {escape(row['comment'] or 'Без комментария')}")

    @staticmethod
    def decision_buttons(row):
        options = []
        if row["status"] == "pending":
            options.append(button("✅ Записать", f"adm:approve:{row['id']}"))
        if row["status"] in ("pending", "confirmed"):
            options.append(button("❌ Отменить", f"adm:cancel:{row['id']}"))
        return [options] if options else []

    @staticmethod
    def page_rows(items, page, prefix):
        last_page = max(0, (len(items) - 1) // 6)
        page = max(0, min(page, last_page))
        navigation = []
        if page > 0:
            navigation.append(button("← Предыдущие", f"{prefix}:{page - 1}"))
        if page < last_page:
            navigation.append(button("Следующие →", f"{prefix}:{page + 1}"))
        return items[page * 6:page * 6 + 6], [navigation] if navigation else []

    def admin_list(self, chat_id, page):
        items, navigation = self.page_rows(self.store.upcoming(), page, "adm:list")
        rows = []
        text = "📋 <b>Предстоящие записи и заявки</b>\n"
        if not items:
            text += "\nЗаписей пока нет."
        for row in items:
            text += (f"\n#{row['id']} · {day_label(row['day'])} · {interval(row['hour'])}\n"
                     f"{escape(row['name'][:80])} · {STATUSES[row['status']]}\n")
            rows.append([button(f"Открыть запись №{row['id']}", f"adm:view:{row['id']}")])
        self.screen(chat_id, text, rows + navigation + [back("adm:home")])

    def admin_breaks(self, chat_id, page):
        items, navigation = self.page_rows(self.store.list_breaks(), page, "adm:breaklist")
        text = "☕ <b>Мои перерывы</b>\n"
        rows = []
        for row in items:
            text += f"\n#{row['id']} · {day_label(row['day'])} · {row['start_hour']:02d}:00–{row['end_hour']:02d}:00\n"
            rows.append([button(f"Удалить перерыв №{row['id']}", f"adm:unbreak:{row['id']}")])
        if not items:
            text += "\nПерерывов пока нет."
        self.screen(chat_id, text, rows + navigation + [back("adm:home")])

    def on_message(self, message):
        if message.chat.type != "private":
            return
        chat_id = message.chat.id
        text = (message.text or "").strip()
        command = text.split(maxsplit=1)[0].split("@")[0] if text else ""
        try:
            if command in ("/start", "/help", "/cancel"):
                self.home(chat_id, fresh=True)
            elif command == "/id":
                self.bot.send_message(chat_id, f"Ваш Telegram ID: <code>{message.from_user.id}</code>", parse_mode="HTML")
            elif command == "/admin":
                if message.from_user.id != self.config.admin_id:
                    raise BookingError("Админ-панель доступна только администратору.")
                self.admin_home(chat_id)
            elif command.startswith("/"):
                raise BookingError("Неизвестная команда. Главное меню: /start")
            else:
                session = self.sessions.get(chat_id, {})
                if session.get("step") == "comment":
                    if not text or len(text) > 1000:
                        raise BookingError("Отправьте текст до 1000 символов или нажмите «Пропустить».")
                    session["comment"] = text
                    self.phone_prompt(chat_id)
                elif session.get("step") == "phone":
                    if message.content_type == "contact":
                        if message.contact.user_id != message.from_user.id:
                            raise BookingError("Отправьте свой контакт или введите номер текстом.")
                        text = message.contact.phone_number
                    if not re.fullmatch(r"\+?[\d ()-]{7,32}", text) or not 7 <= len(re.sub(r"\D", "", text)) <= 15:
                        raise BookingError("Проверьте номер: 7–15 цифр, можно использовать +, пробелы, скобки и дефисы.")
                    session["phone"] = text
                    self.review(chat_id)
                else:
                    self.bot.send_message(chat_id, "Используйте кнопки в последнем меню или команду /start.")
        except BookingError as exc:
            self.bot.send_message(chat_id, str(exc))
        except Exception as exc:
            LOG.error("Message handler failed: %s", type(exc).__name__)
            self.bot.send_message(chat_id, "Не удалось выполнить действие. Попробуйте ещё раз или откройте /start.")

    def on_callback(self, call):
        if not call.message or call.message.chat.type != "private":
            self.bot.answer_callback_query(call.id, "Откройте личный чат с ботом.")
            return
        chat_id = call.message.chat.id
        data = call.data or ""
        try:
            if call.from_user.id != chat_id:
                raise BookingError("Эта кнопка доступна только владельцу чата.")
            if data.startswith("adm:"):
                if call.from_user.id != self.config.admin_id:
                    raise BookingError("Админ-панель доступна только администратору.")
                self.admin_callback(chat_id, data, call.message.message_id)
            else:
                if self.panels.get(chat_id) != call.message.message_id:
                    raise BookingError("Это меню устарело. Используйте последнее меню или /start.")
                self.client_callback(chat_id, data, call.from_user)
            self.bot.answer_callback_query(call.id)
        except (BookingError, ValueError, KeyError, IndexError) as exc:
            message = str(exc) if isinstance(exc, BookingError) else "Эта кнопка устарела. Откройте /start."
            self.bot.answer_callback_query(call.id, message, show_alert=True)
        except Exception as exc:
            LOG.error("Callback handler failed: %s", type(exc).__name__)
            self.bot.answer_callback_query(call.id, "Не удалось выполнить действие. Попробуйте ещё раз.", show_alert=True)

    def client_callback(self, chat_id, data, user):
        session = self.sessions.get(chat_id, {})
        step = session.get("step")
        if data == "home":
            self.home(chat_id)
        elif data == "book":
            self.sessions[chat_id] = {}
            self.show_days(chat_id)
        elif data == "details":
            self.screen(chat_id, DETAILS, [self.manager_button(), back()])
        elif data == "prices":
            self.screen(chat_id, PRICES, [self.manager_button(), back()])
        elif data == "reviews":
            self.screen(chat_id, "💬 <b>Отзывы</b>\n\nОтзывы о встречах доступны в Telegram-канале.\n"
                        "Если остались вопросы, напишите менеджеру @h010dok.",
                        [[button("📣 Читать отзывы", url="https://t.me/otzivi0Vorobev")], self.manager_button(), back()])
        elif data.startswith("day:") and step == "day":
            day = data.split(":")[1]
            self.store.valid_day(day)
            session["day"] = day
            session.pop("hour", None)
            self.show_times(chat_id)
        elif data.startswith("hour:") and step == "time":
            hour = int(data.split(":")[1])
            self.store.validate_slot(session["day"], hour)
            if hour not in self.store.available_hours(session["day"]):
                self.show_times(chat_id)
                raise BookingError("Это время уже занято. Выберите другое.")
            session["hour"] = hour
            self.comment_prompt(chat_id)
        elif data == "skip:comment" and step == "comment":
            session["comment"] = ""
            self.phone_prompt(chat_id)
        elif data == "skip:phone" and step == "phone":
            session["phone"] = ""
            self.review(chat_id)
        elif data == "booking:back":
            previous = {"day": self.home, "time": self.show_days, "comment": self.show_times,
                        "phone": self.comment_prompt, "review": self.phone_prompt}
            if step not in previous:
                raise BookingError("Начните запись заново: /start")
            previous[step](chat_id)
        elif data == "submit" and step == "review":
            try:
                booking_id = self.store.reserve(user.id, user.full_name, user.username or "",
                                                session["day"], session["hour"],
                                                session.get("comment", ""), session.get("phone", ""))
            except BookingError:
                # A competing reservation or an admin break may have appeared during input.
                try:
                    self.show_times(chat_id)
                except BookingError:
                    self.show_days(chat_id)
                raise
            self.sessions.pop(chat_id, None)
            self.screen(chat_id, f"⏳ <b>Заявка №{booking_id} отправлена</b>\n\n"
                        f"📅 {day_label(session['day'])}\n🕒 {interval(session['hour'])}\n"
                        f"Часовой пояс: {escape(self.config.timezone)}.\n\n"
                        "Время зарезервировано. Администратор рассмотрит заявку, "
                        "и бот сообщит о подтверждении или отмене.", [back()])
        else:
            raise BookingError("Эта кнопка устарела. Используйте последнее меню или /start.")

    def admin_callback(self, chat_id, data, message_id):
        parts = data.split(":")
        action = parts[1]
        if action == "home":
            self.admin_home(chat_id)
        elif action == "list":
            self.admin_list(chat_id, int(parts[2]))
        elif action == "view":
            row = self.store.get_booking(int(parts[2]))
            self.screen(chat_id, self.booking_text(row), self.decision_buttons(row) + [back("adm:list:0")])
        elif action in ("approve", "cancel"):
            row = self.store.decide(int(parts[2]), action == "approve")
            # Update the actual notification card, even if it is not the current menu.
            try:
                self.bot.edit_message_text(self.booking_text(row), chat_id, message_id,
                                           parse_mode="HTML", reply_markup=keyboard([back("adm:home")]))
            except ApiTelegramException:
                self.bot.send_message(chat_id, f"Запись №{row['id']}: {STATUSES[row['status']]}")
        elif action == "breakdays":
            rows = [[button(day_label(day), f"adm:breakstart:{day}")] for day in self.store.days()]
            self.screen(chat_id, "☕ Выберите дату перерыва:", rows + [back("adm:home")])
        elif action == "breakstart":
            day = parts[2]
            self.store.valid_day(day)
            options = [button(f"{hour:02d}:00", f"adm:breakend:{day}:{hour}") for hour in range(8, 18)
                       if self.store.slot_time(day, hour + 1) > self.store.now()]
            rows = [options[i:i + 3] for i in range(0, len(options), 3)]
            self.screen(chat_id, f"☕ {day_label(day)}\n\nВыберите начало перерыва.\n"
                        "Перерывы задаются по часам, как сеансы.", rows + [back("adm:breakdays")])
        elif action == "breakend":
            day, start = parts[2], int(parts[3])
            self.store.valid_day(day)
            if not 8 <= start < 18:
                raise BookingError("Недопустимое начало перерыва.")
            options = [button(f"{end:02d}:00", f"adm:breaksave:{day}:{start}:{end}")
                       for end in range(start + 1, 19)]
            rows = [options[i:i + 3] for i in range(0, len(options), 3)]
            self.screen(chat_id, f"☕ {day_label(day)}, с {start:02d}:00\n\nВыберите конец перерыва:",
                        rows + [back(f"adm:breakstart:{day}")])
        elif action == "breaksave":
            day, start, end = parts[2], int(parts[3]), int(parts[4])
            self.store.add_break(day, start, end)
            self.screen(chat_id, f"☕ <b>Перерыв добавлен</b>\n\n{day_label(day)}\n"
                        f"{start:02d}:00–{end:02d}:00\nВ это время записаться нельзя.",
                        [back("adm:home")])
        elif action == "breaklist":
            self.admin_breaks(chat_id, int(parts[2]))
        elif action == "unbreak":
            self.store.remove_break(int(parts[2]))
            self.admin_breaks(chat_id, 0)
        else:
            raise BookingError("Неизвестное действие. Откройте /admin.")

    def deliver_notifications(self):
        """At-least-once delivery: transient API errors do not lose decisions."""
        for event in self.store.notifications():
            try:
                row = self.store.get_booking(event["booking_id"])
                kind = event["kind"]
                if kind == "new":
                    if row["status"] == "pending":
                        self.bot.send_message(self.config.admin_id,
                                              "🔔 <b>Новая заявка!</b>\n\n" + self.booking_text(row),
                                              parse_mode="HTML", reply_markup=keyboard(self.decision_buttons(row)))
                elif kind == row["status"]:
                    heading = "✅ <b>Ваша запись подтверждена!</b>" if kind == "confirmed" else "❌ <b>Ваша запись отменена.</b>"
                    self.bot.send_message(row["user_id"],
                                          f"{heading}\n\nЗапись №{row['id']}\n"
                                          f"📅 {day_label(row['day'])}\n🕒 {interval(row['hour'])}\n"
                                          f"Часовой пояс: {escape(self.config.timezone)}.\n\n"
                                          + ("До встречи!" if kind == "confirmed" else "Выбрать другое время: /start"),
                                          parse_mode="HTML", reply_markup=keyboard([self.manager_button()]))
                self.store.notification_result(event["id"], True)
            except Exception as exc:
                LOG.warning("Notification %s failed: %s", event["id"], type(exc).__name__)
                self.store.notification_result(event["id"], False, event["attempts"])

    def notification_loop(self, stop):
        while not stop.is_set():
            try:
                self.deliver_notifications()
            except Exception as exc:
                LOG.error("Notification worker failed: %s", type(exc).__name__)
            stop.wait(3)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        config = Config.from_env()
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    # Serial update processing keeps each user's interactive form consistent.
    bot = telebot.TeleBot(config.token, threaded=False, parse_mode="HTML")
    application = BookingBot(bot, Store(config.database, config.timezone), config)
    bot.set_my_commands([types.BotCommand("start", "Главное меню"),
                         types.BotCommand("cancel", "Сбросить ввод и вернуться в меню"),
                         types.BotCommand("id", "Мой Telegram ID")])
    stop = Event()
    worker = Thread(target=application.notification_loop, args=(stop,), daemon=True)
    worker.start()
    LOG.info("Бот запущен. Часовой пояс: %s", config.timezone)
    try:
        bot.infinity_polling(skip_pending=False, timeout=30, long_polling_timeout=30,
                             allowed_updates=["message", "callback_query"])
    finally:
        stop.set()
        worker.join(timeout=5)


if __name__ == "__main__":
    main()
