"""
config/settings.py
All environment-driven configuration for LinguaBot.
Copy .env.example → .env and fill in the values.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Core ──────────────────────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise EnvironmentError("BOT_TOKEN is not set. Check your .env file.")

# ── Translation back-end ──────────────────────────────────────────────────────
# Supported values: "google" | "deepl" | "libre"
TRANSLATION_PROVIDER: str = os.getenv("TRANSLATION_PROVIDER", "google")

# Google Cloud Translation API key  (used when TRANSLATION_PROVIDER=google)
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")

# DeepL API key  (used when TRANSLATION_PROVIDER=deepl)
DEEPL_API_KEY: str = os.getenv("DEEPL_API_KEY", "")

# LibreTranslate instance URL  (used when TRANSLATION_PROVIDER=libre)
LIBRE_API_URL: str = os.getenv("LIBRE_API_URL", "https://libretranslate.com")
LIBRE_API_KEY: str = os.getenv("LIBRE_API_KEY", "")

# ── Database ──────────────────────────────────────────────────────────────────
# SQLite path (relative to project root) or full absolute path
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/linguabot.db")

# ── Cache ─────────────────────────────────────────────────────────────────────
# Max translation entries kept in the in-process LRU cache
CACHE_MAX_SIZE: int = int(os.getenv("CACHE_MAX_SIZE", "2000"))
# Seconds before a cached translation expires
CACHE_TTL: int = int(os.getenv("CACHE_TTL", "3600"))

# ── Behaviour ─────────────────────────────────────────────────────────────────
# Minimum characters a message must have to be translated (avoids noise)
MIN_MESSAGE_LENGTH: int = int(os.getenv("MIN_MESSAGE_LENGTH", "2"))

# Show original text below the translation?  1 = yes, 0 = no
SHOW_ORIGINAL: bool = os.getenv("SHOW_ORIGINAL", "0") == "1"

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
