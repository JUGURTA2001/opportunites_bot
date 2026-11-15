import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "data/bot.db")
SOURCES_PATH = os.getenv("SOURCES_PATH", "sources.json")

try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0

# Intervalle entre deux vérifications des sources (minimum 5 minutes, par politesse envers les sites).
try:
    CHECK_INTERVAL_MINUTES = max(5, int(os.getenv("CHECK_INTERVAL_MINUTES", "30")))
except ValueError:
    CHECK_INTERVAL_MINUTES = 30
