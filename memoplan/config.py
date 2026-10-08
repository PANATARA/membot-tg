"""
Configuration module for MemoPlan Telegram Bot.
"""
from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Load environment variables
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv()


@dataclass(frozen=True)
class Config:
    # Bot API Token
    BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    # Optional Proxy URL (e.g. socks5://127.0.0.1:10808 or http://127.0.0.1:7890)
    PROXY_URL: str = os.getenv("TELEGRAM_PROXY_URL", os.getenv("HTTPS_PROXY", os.getenv("ALL_PROXY", ""))).strip()

    # SQLite database path
    DATABASE_PATH: Path = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "memoplan.db")))

    # Default sleep settings
    DEFAULT_SLEEP_START_HOUR: int = int(os.getenv("DEFAULT_SLEEP_START_HOUR", "23"))  # 23:00
    DEFAULT_SLEEP_END_HOUR: int = int(os.getenv("DEFAULT_SLEEP_END_HOUR", "9"))     # 09:00
    DEFAULT_TIMEZONE_OFFSET: int = int(os.getenv("DEFAULT_TIMEZONE_OFFSET", "3"))    # UTC+3 (MSK)

    # Notifier settings
    NOTIFICATION_CHECK_INTERVAL_SECONDS: int = int(os.getenv("NOTIFICATION_CHECK_INTERVAL_SECONDS", "60"))
    NOTIFICATION_COOLDOWN_HOURS: int = int(os.getenv("NOTIFICATION_COOLDOWN_HOURS", "3"))

    # Soon interval threshold: topics due within next N hours are considered "Soon"
    SOON_THRESHOLD_HOURS: int = int(os.getenv("SOON_THRESHOLD_HOURS", "24"))


config = Config()
