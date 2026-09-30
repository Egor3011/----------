import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import Config
from main import BookingBot
from storage import BookingError, Store


NOW = datetime(2026, 9, 30, 10, 30, tzinfo=ZoneInfo("Europe/Moscow"))
DAY = "2026-10-01"


class FakeBot:
    def __init__(self):
        self.messages = []
        self.edits = []
        self.answers = []
        self.fail_sends = False

    def register_message_handler(self, *args, **kwargs):
        pass

    def register_callback_query_handler(self, *args, **kwargs):
        pass

    def send_message(self, chat_id, text, **kwargs):
        if self.fail_sends:
            raise ConnectionError("Simulated Telegram outage")
        self.messages.append((chat_id, text, kwargs))
        return SimpleNamespace(message_id=len(self.messages))

    def edit_message_text(self, text, chat_id, message_id, **kwargs):
        self.edits.append((chat_id, text, kwargs))

    def answer_callback_query(self, call_id, text="", **kwargs):
        self.answers.append((call_id, text, kwargs))


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "test.sqlite3"
        self.store = Store(self.path, now=lambda: NOW)

    def tearDown(self):
        self.directory.cleanup()

    def reserve(self, day=DAY, hour=10, user_id=20, **kwargs):
        return self.store.reserve(user_id, "Клиент", "client", day, hour, **kwargs)


class ScheduleTests(BaseCase):
    def test_calendar_boundaries_and_sunday(self):
        self.assertIn("2026-10-14", self.store.days())
        self.assertNotIn("2026-10-15", self.store.days())
        self.assertNotIn("2026-10-04", self.store.days())
        for day in ("2026-10-04", "2026-10-15", "2026-09-29", "invalid"):
            with self.subTest(day=day), self.assertRaises(BookingError):
                self.reserve(day=day)

    def test_past_times_and_workday_end(self):
        self.assertEqual(self.store.available_hours("2026-09-30"), list(range(11, 18)))
        for hour in (7, 18, 23):
            with self.subTest(hour=hour), self.assertRaises(BookingError):
                self.reserve(hour=hour)
        with self.assertRaises(BookingError):
            self.reserve(day="2026-09-30", hour=10)
        self.reserve(hour=17)

    def test_pending_and_confirmed_slots_block_until_cancelled(self):
        booking_id = self.reserve()
        self.assertNotIn(10, self.store.available_hours(DAY))
        with self.assertRaises(BookingError):
            self.reserve(user_id=21)
        self.store.decide(booking_id, True)
        self.assertNotIn(10, self.store.available_hours(DAY))
        self.store.decide(booking_id, False)
        self.assertIn(10, self.store.available_hours(DAY))
        self.reserve(user_id=21)

    def test_decisions_are_idempotent(self):
        booking_id = self.reserve()
        self.store.decide(booking_id, True)
        with self.assertRaises(BookingError):
            self.store.decide(booking_id, True)
        self.store.decide(booking_id, False)
        with self.assertRaises(BookingError):
            self.store.decide(booking_id, False)
        self.assertEqual(len(self.store.notifications()), 3)

    def test_concurrent_clients_cannot_reserve_same_slot(self):
        barrier = Barrier(8)

        def attempt(index):
            barrier.wait()
            try:
                self.reserve(user_id=index)
                return True
            except BookingError:
                return False

        with ThreadPoolExecutor(max_workers=8) as executor:
            self.assertEqual(sum(executor.map(attempt, range(8))), 1)

    def test_booking_racing_break_has_exactly_one_winner(self):
        barrier = Barrier(2)

        def attempt(is_break):
            barrier.wait()
            try:
                if is_break:
                    self.store.add_break(DAY, 10, 11)
                else:
                    self.reserve()
                return True
            except BookingError:
                return False

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sum(executor.map(attempt, [False, True])), 1)

    def test_breaks_block_hours_and_can_be_removed(self):
        break_id = self.store.add_break(DAY, 10, 13)
        self.assertEqual(self.store.available_hours(DAY), [8, 9, 13, 14, 15, 16, 17])
        with self.assertRaises(BookingError):
            self.reserve(hour=12)
        self.reserve(hour=13)
        self.store.remove_break(break_id)
        self.assertIn(10, self.store.available_hours(DAY))

    def test_breaks_cannot_overlap_bookings_or_other_breaks(self):
        self.reserve()
        with self.assertRaises(BookingError):
            self.store.add_break(DAY, 9, 11)
        self.store.add_break(DAY, 11, 12)
        with self.assertRaises(BookingError):
            self.store.add_break(DAY, 11, 13)
        for start, end in ((7, 9), (17, 19), (10, 10), (11, 10)):
            with self.subTest(start=start, end=end), self.assertRaises(BookingError):
                self.store.add_break(DAY, start, end)

    def test_full_day_break_and_sunday(self):
        self.store.add_break(DAY, 8, 18)
        self.assertEqual(self.store.available_hours(DAY), [])
        with self.assertRaises(BookingError):
            self.store.add_break("2026-10-04", 8, 18)

    def test_schedule_and_notifications_survive_restart(self):
        booking_id = self.reserve(comment="Комментарий", phone="+79991234567")
        self.store.add_break(DAY, 12, 14)
        reopened = Store(self.path, now=lambda: NOW)
        self.assertEqual(reopened.get_booking(booking_id)["comment"], "Комментарий")
        self.assertEqual(len(reopened.list_breaks()), 1)
        self.assertNotIn(10, reopened.available_hours(DAY))
        self.assertNotIn(12, reopened.available_hours(DAY))
        self.assertEqual(len(reopened.notifications()), 1)

    def test_overdue_pending_request_can_be_cancelled_but_not_confirmed(self):
        booking_id = self.reserve()
        self.store._now = lambda: NOW.replace(month=10, day=2)
        self.assertEqual(self.store.upcoming()[0]["id"], booking_id)
        with self.assertRaises(BookingError):
            self.store.decide(booking_id, True)
        self.store.decide(booking_id, False)


class ConversationTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.bot = FakeBot()
        self.config = Config("test", 99, self.path)
        self.app = BookingBot(self.bot, self.store, self.config)

    @staticmethod
    def user(user_id):
        return SimpleNamespace(id=user_id, full_name="<Иван & Анна>", username="client")

    def message(self, text, user_id=20, contact=None):
        return SimpleNamespace(chat=SimpleNamespace(id=user_id, type="private"), text=text,
                               from_user=self.user(user_id), contact=contact,
                               content_type="contact" if contact else "text")

    def click(self, data, user_id=20, message_id=None):
        self.app.on_callback(SimpleNamespace(id="callback", data=data, from_user=self.user(user_id),
                                             message=SimpleNamespace(chat=SimpleNamespace(id=user_id, type="private"),
                                             message_id=message_id or self.app.panels.get(user_id, 1))))

    def start_form(self):
        self.app.on_message(self.message("/start"))
        self.click("book")
        self.click(f"day:{DAY}")
        self.click("hour:10")

    def submit_form(self):
        self.start_form()
        self.click("skip:comment")
        self.click("skip:phone")
        self.click("submit")

    def test_complete_booking_and_admin_confirmation(self):
        self.start_form()
        self.app.on_message(self.message("Тревога <b>и</b> сон"))
        self.app.on_message(self.message("+7 999 123-45-67"))
        self.click("submit")
        row = self.store.upcoming()[0]
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["comment"], "Тревога <b>и</b> сон")
        self.app.deliver_notifications()
        recipient, text, options = self.bot.messages[-1]
        self.assertEqual(recipient, 99)
        self.assertIn("&lt;b&gt;и&lt;/b&gt;", text)
        self.assertIn("&lt;Иван &amp; Анна&gt;", text)
        self.assertEqual(options["reply_markup"].keyboard[0][0].callback_data, f"adm:approve:{row['id']}")
        self.click(f"adm:approve:{row['id']}", user_id=99)
        self.app.deliver_notifications()
        self.assertEqual(self.bot.messages[-1][0], 20)
        self.assertIn("подтверждена", self.bot.messages[-1][1])
        self.assertEqual(self.store.get_booking(row["id"])["status"], "confirmed")

    def test_optional_fields_and_duplicate_submit(self):
        self.submit_form()
        self.click("submit")
        self.assertEqual(len(self.store.upcoming()), 1)
        self.assertEqual(self.store.upcoming()[0]["phone"], "")
        self.assertIn("устарела", self.bot.answers[-1][1])

    def test_back_buttons_follow_previous_step(self):
        self.start_form()
        self.click("booking:back")
        self.assertEqual(self.app.sessions[20]["step"], "time")
        self.click("hour:11")
        self.click("skip:comment")
        self.click("booking:back")
        self.assertEqual(self.app.sessions[20]["step"], "comment")
        self.click("skip:comment")
        self.click("skip:phone")
        self.click("booking:back")
        self.assertEqual(self.app.sessions[20]["step"], "phone")

    def test_old_panel_cannot_submit_or_change_current_form(self):
        self.start_form()
        old_panel = self.app.panels[20]
        self.app.on_message(self.message("/start"))
        self.click("book", message_id=old_panel)
        self.assertNotIn(20, self.app.sessions)
        self.assertIn("устарело", self.bot.answers[-1][1])

    def test_non_admin_cannot_access_any_admin_action(self):
        booking_id = self.reserve()
        for action in ("adm:home", "adm:list:0", f"adm:approve:{booking_id}",
                       f"adm:cancel:{booking_id}", f"adm:breaksave:{DAY}:12:13", "adm:unbreak:1"):
            with self.subTest(action=action):
                self.click(action)
                self.assertIn("только администратору", self.bot.answers[-1][1])
        self.assertEqual(self.store.get_booking(booking_id)["status"], "pending")
        self.assertEqual(self.store.list_breaks(), [])

    def test_rejection_notifies_client_and_frees_slot(self):
        self.submit_form()
        booking_id = self.store.upcoming()[0]["id"]
        self.click(f"adm:cancel:{booking_id}", user_id=99)
        self.app.deliver_notifications()
        self.assertIn("отменена", self.bot.messages[-1][1])
        self.assertIn(10, self.store.available_hours(DAY))

    def test_break_created_during_form_prevents_submission(self):
        self.start_form()
        self.click("skip:comment")
        self.click("skip:phone")
        self.store.add_break(DAY, 10, 11)
        self.click("submit")
        self.assertEqual(self.store.upcoming(), [])
        self.assertEqual(self.app.sessions[20]["step"], "time")
        self.assertIn("занято", self.bot.answers[-1][1])

    def test_failed_notification_is_persisted_and_retried(self):
        self.reserve()
        self.bot.fail_sends = True
        self.app.deliver_notifications()
        self.assertEqual(self.store.notifications(), [])  # Backoff, not deletion.
        with self.store.connect(write=True) as db:
            event = db.execute("SELECT * FROM outbox").fetchone()
            self.assertEqual(event["sent"], 0)
            self.assertEqual(event["attempts"], 1)
            db.execute("UPDATE outbox SET next_attempt=0")
        self.bot.fail_sends = False
        restarted = BookingBot(self.bot, Store(self.path, now=lambda: NOW), self.config)
        restarted.deliver_notifications()
        self.assertEqual(self.bot.messages[-1][0], 99)
        self.assertEqual(self.store.notifications(), [])

    def test_cancelled_booking_does_not_send_outdated_confirmation(self):
        booking_id = self.reserve()
        self.store.decide(booking_id, True)
        self.store.decide(booking_id, False)
        self.app.deliver_notifications()
        self.assertEqual(len(self.bot.messages), 1)
        self.assertIn("отменена", self.bot.messages[0][1])

    def test_phone_validation_and_contact_ownership(self):
        self.start_form()
        self.click("skip:comment")
        self.app.on_message(self.message("123"))
        self.assertEqual(self.app.sessions[20]["step"], "phone")
        self.app.on_message(self.message(None, contact=SimpleNamespace(user_id=21, phone_number="79991234567")))
        self.assertEqual(self.app.sessions[20]["step"], "phone")
        self.app.on_message(self.message(None, contact=SimpleNamespace(user_id=20, phone_number="79991234567")))
        self.assertEqual(self.app.sessions[20]["step"], "review")

    def test_admin_break_flow_and_removal(self):
        self.app.on_message(self.message("/admin", user_id=99))
        for data in ("adm:breakdays", f"adm:breakstart:{DAY}", f"adm:breakend:{DAY}:12",
                     f"adm:breaksave:{DAY}:12:14"):
            self.click(data, user_id=99)
        self.assertEqual(len(self.store.list_breaks()), 1)
        self.assertNotIn(12, self.store.available_hours(DAY))
        self.click("adm:unbreak:1", user_id=99)
        self.assertIn(12, self.store.available_hours(DAY))

    def test_only_admin_sees_admin_menu(self):
        for user_id in (20, 99):
            self.app.home(user_id, fresh=True)
            buttons = [item.callback_data for row in self.bot.messages[-1][2]["reply_markup"].keyboard for item in row]
            self.assertEqual("adm:home" in buttons, user_id == 99)


if __name__ == "__main__":
    unittest.main()
