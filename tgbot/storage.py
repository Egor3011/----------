"""Persistent schedule and atomic reservations. All times use the configured zone."""
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


class BookingError(ValueError):
    pass


class Store:
    def __init__(self, path, timezone="Europe/Moscow", now=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.zone = ZoneInfo(timezone)
        self._now = now or (lambda: datetime.now(self.zone))
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS bookings (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    username TEXT NOT NULL,
                    day TEXT NOT NULL,
                    hour INTEGER NOT NULL CHECK(hour BETWEEN 8 AND 17),
                    comment TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK(status IN ('pending','confirmed','cancelled')),
                    created_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS reserved_slot ON bookings(day, hour)
                    WHERE status IN ('pending', 'confirmed');
                CREATE TABLE IF NOT EXISTS breaks (
                    id INTEGER PRIMARY KEY,
                    day TEXT NOT NULL,
                    start_hour INTEGER NOT NULL,
                    end_hour INTEGER NOT NULL,
                    CHECK(start_hour >= 8 AND end_hour <= 18 AND start_hour < end_hour)
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY,
                    booking_id INTEGER NOT NULL REFERENCES bookings(id),
                    kind TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL DEFAULT 0,
                    sent INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(booking_id, kind)
                );
            """)

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def now(self):
        return self._now().astimezone(self.zone)

    def valid_day(self, day):
        try:
            value = date.fromisoformat(day)
        except (TypeError, ValueError):
            raise BookingError("Некорректная дата.") from None
        today = self.now().date()
        if not today <= value <= today + timedelta(days=14):
            raise BookingError("Выберите дату в пределах ближайших двух недель.")
        if value.weekday() == 6:
            raise BookingError("Воскресенье — выходной.")
        return value

    def slot_time(self, day, hour):
        return datetime.combine(date.fromisoformat(day), datetime.min.time(), self.zone).replace(hour=hour)

    def validate_slot(self, day, hour):
        self.valid_day(day)
        if not 8 <= hour < 18:
            raise BookingError("Встречи начинаются с 08:00 до 17:00 и длятся 60 минут.")
        if self.slot_time(day, hour) <= self.now():
            raise BookingError("Это время уже прошло. Выберите другое.")

    @staticmethod
    def occupied(db, day, hour):
        return bool(db.execute("""
            SELECT 1 FROM bookings WHERE day=? AND hour=? AND status IN ('pending','confirmed')
            UNION ALL SELECT 1 FROM breaks WHERE day=? AND start_hour<=? AND end_hour>?
        """, (day, hour, day, hour, hour)).fetchone())

    def available_hours(self, day):
        self.valid_day(day)
        now = self.now()
        with self.connect() as db:
            return [hour for hour in range(8, 18)
                    if self.slot_time(day, hour) > now and not self.occupied(db, day, hour)]

    def days(self):
        today = self.now().date()
        return [(today + timedelta(days=i)).isoformat() for i in range(15)
                if (today + timedelta(days=i)).weekday() != 6]

    def reserve(self, user_id, name, username, day, hour, comment="", phone=""):
        if len(comment) > 1000 or len(phone) > 32:
            raise BookingError("Слишком длинный комментарий или телефон.")
        with self.connect(write=True) as db:
            self.validate_slot(day, hour)
            if self.occupied(db, day, hour):
                raise BookingError("Это время уже занято. Выберите другое.")
            cursor = db.execute("""
                INSERT INTO bookings(user_id,name,username,day,hour,comment,phone,status,created_at)
                VALUES(?,?,?,?,?,?,?,'pending',?)
            """, (user_id, name, username, day, hour, comment, phone, self.now().isoformat()))
            booking_id = cursor.lastrowid
            db.execute("INSERT INTO outbox(booking_id,kind) VALUES(?,'new')", (booking_id,))
        return booking_id

    def get_booking(self, booking_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
            if not row:
                raise BookingError("Запись не найдена.")
            return dict(row)

    def decide(self, booking_id, confirm):
        with self.connect(write=True) as db:
            row = db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
            if not row:
                raise BookingError("Запись не найдена.")
            if row["status"] == "cancelled" or (confirm and row["status"] != "pending"):
                raise BookingError("Эта заявка уже обработана.")
            if confirm and self.slot_time(row["day"], row["hour"]) <= self.now():
                raise BookingError("Время встречи уже прошло. Заявку можно отменить.")
            status = "confirmed" if confirm else "cancelled"
            db.execute("UPDATE bookings SET status=? WHERE id=?", (status, booking_id))
            db.execute("INSERT INTO outbox(booking_id,kind) VALUES(?,?)", (booking_id, status))
        return self.get_booking(booking_id)

    def upcoming(self):
        with self.connect() as db:
            rows = db.execute("""SELECT * FROM bookings
                WHERE status IN ('pending','confirmed') AND day>=? ORDER BY day,hour
            """, (self.now().date().isoformat(),)).fetchall()
        # Include a meeting until its end, and all pending requests (even overdue ones).
        active = [dict(row) for row in rows
                  if self.slot_time(row["day"], row["hour"]) + timedelta(hours=1) > self.now()]
        with self.connect() as db:
            overdue = [dict(row) for row in db.execute("""SELECT * FROM bookings
                WHERE status='pending' ORDER BY day,hour""")
                if row["id"] not in {item["id"] for item in active}]
        return sorted(active + overdue, key=lambda row: (row["day"], row["hour"]))

    def add_break(self, day, start, end):
        with self.connect(write=True) as db:
            self.valid_day(day)
            if not 8 <= start < end <= 18:
                raise BookingError("Перерыв должен быть внутри рабочего дня: 08:00–18:00.")
            if self.slot_time(day, end) <= self.now():
                raise BookingError("Этот перерыв уже закончился.")
            if any(self.occupied(db, day, hour) for hour in range(start, end)):
                raise BookingError("Перерыв пересекается с заявкой, записью или другим перерывом.")
            return db.execute("INSERT INTO breaks(day,start_hour,end_hour) VALUES(?,?,?)",
                              (day, start, end)).lastrowid

    def list_breaks(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM breaks WHERE day>=? ORDER BY day,start_hour",
                (self.now().date().isoformat(),))]

    def remove_break(self, break_id):
        with self.connect(write=True) as db:
            if not db.execute("DELETE FROM breaks WHERE id=?", (break_id,)).rowcount:
                raise BookingError("Этот перерыв уже удалён.")

    def notifications(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM outbox WHERE sent=0 AND next_attempt<=? ORDER BY id LIMIT 20",
                (time.time(),))]

    def notification_result(self, event_id, success, attempts=0):
        with self.connect(write=True) as db:
            if success:
                db.execute("UPDATE outbox SET sent=1 WHERE id=?", (event_id,))
            else:
                delay = min(3600, 5 * 2 ** min(attempts, 10))
                db.execute("UPDATE outbox SET attempts=attempts+1,next_attempt=? WHERE id=?",
                           (time.time() + delay, event_id))
