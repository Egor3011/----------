"""Configuration is read only at startup; importing modules never starts the bot."""
import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Config:
    token: str
    admin_id: int
    database: Path
    timezone: str = "Europe/Moscow"
    manager: str = "h010dok"

    @classmethod
    def from_env(cls):
        load_dotenv(BASE_DIR / ".env")
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token or token == "replace_with_botfather_token":
            raise ValueError("Укажите BOT_TOKEN в tgbot/.env")
        try:
            admin_id = int(os.getenv("ADMIN_ID", "0"))
            if admin_id <= 0:
                raise ValueError
        except ValueError:
            raise ValueError("Укажите положительный числовой ADMIN_ID в tgbot/.env") from None
        timezone = os.getenv("BOT_TIMEZONE", "Europe/Moscow")
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            raise ValueError("Неизвестный BOT_TIMEZONE") from None
        database = Path(os.getenv("DATABASE_PATH", "data/bot.sqlite3"))
        if not database.is_absolute():
            database = BASE_DIR / database
        return cls(token, admin_id, database, timezone)
