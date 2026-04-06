"""
src/keyboards.py
Inline keyboard builders for the language selection UI.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .languages import SUPPORTED_LANGUAGES, POPULAR_LANGUAGES, get_language_name

_COLS = 3          # buttons per row in the full grid
_PAGE_SIZE = 30    # languages per page in the full list


def language_main_menu(page: int = 0) -> InlineKeyboardMarkup:
    """
    Main language selection menu.
      Page 0 → popular languages  (fast path)
      Page N → alphabetical paginated list
    """
    if page == 0:
        return _popular_keyboard()
    return _paginated_keyboard(page)


def _popular_keyboard() -> InlineKeyboardMarkup:
    rows = []
    chunk = []
    for code in POPULAR_LANGUAGES:
        name = get_language_name(code)
        flag = _flag(code)
        chunk.append(
            InlineKeyboardButton(f"{flag} {name}", callback_data=f"lang:{code}")
        )
        if len(chunk) == _COLS:
            rows.append(chunk)
            chunk = []
    if chunk:
        rows.append(chunk)

    rows.append([
        InlineKeyboardButton("🔠 All languages →", callback_data="lang_page:1"),
    ])
    return InlineKeyboardMarkup(rows)


def _paginated_keyboard(page: int) -> InlineKeyboardMarkup:
    all_langs = sorted(SUPPORTED_LANGUAGES.items(), key=lambda x: x[1])
    total_pages = (len(all_langs) + _PAGE_SIZE - 1) // _PAGE_SIZE
    start = (page - 1) * _PAGE_SIZE
    slice_ = all_langs[start: start + _PAGE_SIZE]

    rows = []
    chunk = []
    for code, name in slice_:
        chunk.append(
            InlineKeyboardButton(f"{_flag(code)} {name}", callback_data=f"lang:{code}")
        )
        if len(chunk) == _COLS:
            rows.append(chunk)
            chunk = []
    if chunk:
        rows.append(chunk)

    # Navigation row
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"lang_page:{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"lang_page:{page + 1}"))
    rows.append(nav)

    rows.append([InlineKeyboardButton("⭐ Popular", callback_data="lang_page:0")])
    return InlineKeyboardMarkup(rows)


def confirm_language(code: str, name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_lang:{code}"),
        InlineKeyboardButton("↩ Back", callback_data="lang_page:0"),
    ]])


def _flag(code: str) -> str:
    """Best-effort regional indicator emoji from a language code."""
    # Map language → most-used country code for the flag emoji
    lang_to_country: dict[str, str] = {
        "en": "gb", "es": "es", "fr": "fr", "de": "de", "it": "it",
        "pt": "pt", "ru": "ru", "uk": "ua", "pl": "pl", "ar": "sa",
        "zh": "cn", "zh-TW": "tw", "ja": "jp", "ko": "kr", "tr": "tr",
        "hi": "in", "nl": "nl", "sv": "se", "da": "dk", "nb": "no",
        "fi": "fi", "cs": "cz", "sk": "sk", "ro": "ro", "bg": "bg",
        "hr": "hr", "sr": "rs", "sl": "si", "hu": "hu", "el": "gr",
        "he": "il", "fa": "ir", "ur": "pk", "vi": "vn", "th": "th",
        "id": "id", "ms": "my", "tl": "ph", "ka": "ge", "hy": "am",
        "kk": "kz", "uz": "uz", "az": "az", "be": "by", "mk": "mk",
        "sq": "al", "bs": "ba", "et": "ee", "lv": "lv", "lt": "lt",
        "is": "is", "ga": "ie", "cy": "gb", "eu": "es", "ca": "es",
        "gl": "es", "mt": "mt", "af": "za", "sw": "ke", "bn": "bd",
        "gu": "in", "hi": "in", "kn": "in", "ml": "in", "mr": "in",
        "pa": "in", "ta": "in", "te": "in", "ne": "np", "si": "lk",
        "km": "kh", "lo": "la", "my": "mm", "mn": "mn", "eo": "eu",
    }
    country = lang_to_country.get(code.lower(), "")
    if not country:
        return "🌐"
    return "".join(chr(0x1F1E6 + ord(c) - ord("a")) for c in country.lower())
