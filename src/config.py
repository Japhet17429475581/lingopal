"""Environment configuration. Core learning works without external services."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'spanish.db').as_posix()}")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://example.com/").strip()
ALLOW_DEV_AUTH = os.getenv("ALLOW_DEV_AUTH", "false").lower() == "true"
INIT_DATA_MAX_AGE = int(os.getenv("INIT_DATA_MAX_AGE", "86400"))
PORT = int(os.getenv("PORT", "3000"))
HOST = os.getenv("HOST", "127.0.0.1" if ALLOW_DEV_AUTH else "0.0.0.0")
 
