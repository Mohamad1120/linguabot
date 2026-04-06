"""
src/translator.py
Unified translation interface with:
  • Multi-provider support  (Google | DeepL | LibreTranslate)
  • Async-safe LRU cache with TTL
  • Automatic source-language detection
  • Graceful fallback on provider errors
"""

import asyncio
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Optional

import aiohttp

from config.settings import (
    TRANSLATION_PROVIDER,
    GOOGLE_API_KEY,
    DEEPL_API_KEY,
    LIBRE_API_URL,
    LIBRE_API_KEY,
    CACHE_MAX_SIZE,
    CACHE_TTL,
)

logger = logging.getLogger(__name__)


# ── Cache ─────────────────────────────────────────────────────────────────────

class _TTLCache:
    """Thread-safe in-process LRU+TTL cache for translations."""

    def __init__(self, max_size: int, ttl: int):
        self._max_size = max_size
        self._ttl = ttl
        self._store: dict[str, tuple[str, float]] = {}   # key → (value, expiry)
        self._lock = asyncio.Lock()

    def _make_key(self, text: str, src: str, tgt: str) -> str:
        raw = f"{tgt}:{src}:{text}"
        return hashlib.md5(raw.encode()).hexdigest()

    async def get(self, text: str, src: str, tgt: str) -> str | None:
        key = self._make_key(text, src, tgt)
        async with self._lock:
            entry = self._store.get(key)
            if entry and time.monotonic() < entry[1]:
                return entry[0]
            if entry:
                del self._store[key]
            return None

    async def set(self, text: str, src: str, tgt: str, translated: str) -> None:
        key = self._make_key(text, src, tgt)
        async with self._lock:
            if len(self._store) >= self._max_size:
                # evict oldest
                oldest = min(self._store, key=lambda k: self._store[k][1])
                del self._store[oldest]
            self._store[key] = (translated, time.monotonic() + self._ttl)


_cache = _TTLCache(max_size=CACHE_MAX_SIZE, ttl=CACHE_TTL)


# ── Provider base ─────────────────────────────────────────────────────────────

class TranslationProvider(ABC):
    @abstractmethod
    async def translate(
        self, text: str, target_lang: str, source_lang: str = "auto"
    ) -> tuple[str, str]:
        """Return (translated_text, detected_source_lang)."""
        ...


# ── Google Cloud Translation ──────────────────────────────────────────────────

class GoogleTranslationProvider(TranslationProvider):
    BASE_URL = "https://translation.googleapis.com/language/translate/v2"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("GOOGLE_API_KEY is required for the Google provider.")
        self._key = api_key

    async def translate(
        self, text: str, target_lang: str, source_lang: str = "auto"
    ) -> tuple[str, str]:
        params: dict = {"q": text, "target": target_lang, "key": self._key, "format": "text"}
        if source_lang != "auto":
            params["source"] = source_lang

        async with aiohttp.ClientSession() as session:
            async with session.post(self.BASE_URL, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()
                t = data["data"]["translations"][0]
                return t["translatedText"], t.get("detectedSourceLanguage", source_lang)


# ── DeepL ─────────────────────────────────────────────────────────────────────

class DeepLTranslationProvider(TranslationProvider):
    BASE_URL = "https://api-free.deepl.com/v2/translate"   # use api.deepl.com for paid

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("DEEPL_API_KEY is required for the DeepL provider.")
        self._key = api_key

    async def translate(
        self, text: str, target_lang: str, source_lang: str = "auto"
    ) -> tuple[str, str]:
        payload: dict = {"text": [text], "target_lang": target_lang.upper(), "auth_key": self._key}
        if source_lang != "auto":
            payload["source_lang"] = source_lang.upper()

        async with aiohttp.ClientSession() as session:
            async with session.post(self.BASE_URL, data=payload) as resp:
                resp.raise_for_status()
                data = await resp.json()
                t = data["translations"][0]
                return t["text"], t.get("detected_source_language", source_lang).lower()


# ── LibreTranslate (self-hosted / free) ───────────────────────────────────────

class LibreTranslationProvider(TranslationProvider):
    def __init__(self, base_url: str, api_key: str = ""):
        self._url = base_url.rstrip("/") + "/translate"
        self._key = api_key

    async def translate(
        self, text: str, target_lang: str, source_lang: str = "auto"
    ) -> tuple[str, str]:
        payload: dict = {
            "q": text,
            "source": source_lang if source_lang != "auto" else "auto",
            "target": target_lang,
            "format": "text",
        }
        if self._key:
            payload["api_key"] = self._key

        async with aiohttp.ClientSession() as session:
            async with session.post(self._url, json=payload) as resp:
                resp.raise_for_status()
                data = await resp.json()
                detected = data.get("detectedLanguage", {}).get("language", source_lang)
                return data["translatedText"], detected


# ── Factory ───────────────────────────────────────────────────────────────────

def _build_provider() -> TranslationProvider:
    provider = TRANSLATION_PROVIDER.lower()
    if provider == "google":
        return GoogleTranslationProvider(GOOGLE_API_KEY)
    if provider == "deepl":
        return DeepLTranslationProvider(DEEPL_API_KEY)
    if provider == "libre":
        return LibreTranslationProvider(LIBRE_API_URL, LIBRE_API_KEY)
    raise ValueError(f"Unknown TRANSLATION_PROVIDER: {TRANSLATION_PROVIDER!r}")


# ── Public façade ─────────────────────────────────────────────────────────────

class Translator:
    """
    Async translator with caching.
    Instantiate once and reuse across the application.
    """

    def __init__(self):
        self._provider: TranslationProvider = _build_provider()
        logger.info("Translation provider: %s", TRANSLATION_PROVIDER)

    async def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: str = "auto",
    ) -> tuple[str, str]:
        """
        Translate *text* to *target_lang*.
        Returns (translated_text, detected_source_lang).
        Uses the cache; calls the provider only on a cache miss.
        """
        # Cache hit?
        cached = await _cache.get(text, source_lang, target_lang)
        if cached is not None:
            return cached, source_lang

        try:
            translated, detected = await self._provider.translate(
                text, target_lang, source_lang
            )
        except Exception as exc:
            logger.error("Translation error (%s → %s): %s", source_lang, target_lang, exc)
            return text, source_lang   # graceful fallback: return original

        await _cache.set(text, detected, target_lang, translated)
        return translated, detected

    async def detect_language(self, text: str) -> str:
        """Quick language detection by translating to English and reading the detected lang."""
        _, detected = await self.translate(text, "en")
        return detected


# Module-level singleton
_translator: Translator | None = None


def get_translator() -> Translator:
    global _translator
    if _translator is None:
        _translator = Translator()
    return _translator
