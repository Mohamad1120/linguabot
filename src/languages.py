"""
src/languages.py
Supported language codes, display names, and helper utilities.
"""

from __future__ import annotations

# ── Supported languages ───────────────────────────────────────────────────────
# Maps BCP-47 / ISO 639-1 code  →  display name (in English)
SUPPORTED_LANGUAGES: dict[str, str] = {
    "af": "Afrikaans",
    "ar": "Arabic",
    "az": "Azerbaijani",
    "be": "Belarusian",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "bs": "Bosnian",
    "ca": "Catalan",
    "cs": "Czech",
    "cy": "Welsh",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "eo": "Esperanto",
    "es": "Spanish",
    "et": "Estonian",
    "eu": "Basque",
    "fa": "Persian",
    "fi": "Finnish",
    "fr": "French",
    "ga": "Irish",
    "gl": "Galician",
    "gu": "Gujarati",
    "he": "Hebrew",
    "hi": "Hindi",
    "hr": "Croatian",
    "hu": "Hungarian",
    "hy": "Armenian",
    "id": "Indonesian",
    "is": "Icelandic",
    "it": "Italian",
    "ja": "Japanese",
    "ka": "Georgian",
    "kk": "Kazakh",
    "km": "Khmer",
    "kn": "Kannada",
    "ko": "Korean",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mk": "Macedonian",
    "ml": "Malayalam",
    "mn": "Mongolian",
    "mr": "Marathi",
    "ms": "Malay",
    "mt": "Maltese",
    "my": "Burmese",
    "nb": "Norwegian",
    "ne": "Nepali",
    "nl": "Dutch",
    "pa": "Punjabi",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sq": "Albanian",
    "sr": "Serbian",
    "sv": "Swedish",
    "sw": "Swahili",
    "ta": "Tamil",
    "te": "Telugu",
    "th": "Thai",
    "tl": "Filipino",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "uz": "Uzbek",
    "vi": "Vietnamese",
    "zh": "Chinese (Simplified)",
    "zh-TW": "Chinese (Traditional)",
}

# Languages shown on the first page of the quick-select keyboard
POPULAR_LANGUAGES: list[str] = [
    "en", "es", "fr", "de", "it", "pt",
    "ru", "uk", "pl", "ar", "zh", "ja",
    "ko", "tr", "hi", "nl",
]


def is_valid_language(code: str) -> bool:
    return code in SUPPORTED_LANGUAGES


def get_language_name(code: str) -> str:
    return SUPPORTED_LANGUAGES.get(code, code.upper())


def search_languages(query: str) -> list[tuple[str, str]]:
    """Return (code, name) pairs whose name contains *query* (case-insensitive)."""
    q = query.lower()
    return [
        (code, name)
        for code, name in SUPPORTED_LANGUAGES.items()
        if q in name.lower() or q == code.lower()
    ]
