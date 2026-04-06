"""
src/handlers.py  —  MLangBot
Redesigned flow:
  • Language setup is PRIVATE (bot DM only) — never visible in the group
  • Messages in group are deleted then reposted as translated versions
  • One repost per unique target language used in that chat
  • Sender always sees their original text (included in the repost header)
  • /setlang in a group sends the user a private DM to configure silently
"""

import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.constants import ParseMode

from config.settings import MIN_MESSAGE_LENGTH, SHOW_ORIGINAL
from .database import Database
from .keyboards import language_main_menu, confirm_language
from .languages import get_language_name, is_valid_language
from .translator import get_translator

logger = logging.getLogger(__name__)

BOT_NAME = "MLangBot"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["db"]


async def _reply(message: Message, text: str, **kwargs) -> None:
    await message.reply_text(text, parse_mode=ParseMode.HTML, **kwargs)


async def _send_private(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    text: str,
    **kwargs,
) -> bool:
    """Send a DM. Returns False if the user hasn't started the bot yet."""
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=ParseMode.HTML,
            **kwargs,
        )
        return True
    except BadRequest:
        return False


# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat

    if chat.type == "private":
        # Check if we were deep-linked from a group (?start=setlang_CHATID)
        if context.args and context.args[0].startswith("setlang_"):
            chat_id = int(context.args[0].split("_")[1])
            context.user_data["pending_setlang_chat"] = chat_id
            db = _db(context)
            current = await db.get_user_language(user.id, chat_id)
            current_name = get_language_name(current) if current else "not set"
            await _reply(
                update.message,
                f"🌐 <b>Set your language for the group</b>\n\n"
                f"Current: <b>{current_name}</b>\n\n"
                "Choose the language you want to read messages in:",
                reply_markup=language_main_menu(page=0),
            )
            return

        await _reply(
            update.message,
            f"👋 Hello, <b>{user.first_name}</b>! I'm <b>{BOT_NAME}</b>.\n\n"
            "I translate group messages so everyone reads them in their own language.\n\n"
            "📌 <b>How to set up:</b>\n"
            "• Add me to a group\n"
            "• Each member sends <b>/setlang</b> in the group\n"
            "• I'll message you privately to pick your language\n"
            "• Done — all messages appear translated for you!\n\n"
            "Use /setlang here to set your default language.",
        )
    else:
        # In a group — nudge user to DM
        await _setlang_group_nudge(update, context)


# ── /help ─────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(
        update.message,
        f"<b>🌐 {BOT_NAME} — Commands</b>\n\n"
        "/setlang — Set your preferred language (private)\n"
        "/mylang — Show your current language\n"
        "/groupstats — Active languages in this group\n"
        "/enable — Enable translations (admin)\n"
        "/disable — Pause translations (admin)\n"
        "/help — Show this message",
    )


# ── /setlang ──────────────────────────────────────────────────────────────────

async def _setlang_group_nudge(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Called when /setlang is used in a group — sends a private deep-link."""
    user = update.effective_user
    chat = update.effective_chat
    bot = context.bot

    deep_link = f"https://t.me/{bot.username}?start=setlang_{chat.id}"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔒 Set my language privately →", url=deep_link)
    ]])

    # Send ephemeral-style notice in group (auto-delete after 8 seconds)
    try:
        sent = await update.message.reply_text(
            "🔒 Language settings are private. Click below to set yours:",
            reply_markup=kb,
        )
        # Delete the user's /setlang command to keep chat clean
        await asyncio.sleep(0.5)
        try:
            await update.message.delete()
        except BadRequest:
            pass
        # Auto-delete the nudge message after 8 s
        await asyncio.sleep(8)
        try:
            await sent.delete()
        except BadRequest:
            pass
    except Exception as exc:
        logger.warning("Could not send setlang nudge: %s", exc)


async def cmd_setlang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user

    if chat.type != "private":
        await _setlang_group_nudge(update, context)
        return

    # In DM — show language picker
    # If a chat context is pending, use it; otherwise use the DM itself
    pending = context.user_data.get("pending_setlang_chat", chat.id)

    db = _db(context)
    current = await db.get_user_language(user.id, pending)
    current_name = get_language_name(current) if current else "not set"

    await _reply(
        update.message,
        f"🌐 <b>Choose your language</b>\n"
        f"Current: <b>{current_name}</b>",
        reply_markup=language_main_menu(page=0),
    )


# ── /mylang ───────────────────────────────────────────────────────────────────

async def cmd_mylang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _db(context)
    user = update.effective_user
    chat = update.effective_chat
    code = await db.get_user_language(user.id, chat.id)
    if code:
        await _reply(update.message, f"🗣 Your language: <b>{get_language_name(code)}</b> ({code})")
    else:
        await _reply(update.message, "You haven't set a language yet.\nUse /setlang to choose one.")


# ── /groupstats ───────────────────────────────────────────────────────────────

async def cmd_groupstats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _db(context)
    chat = update.effective_chat
    users = await db.get_all_users_in_chat(chat.id)
    stats = await db.get_stats(chat.id)

    if not users:
        await _reply(update.message, "No members have set a language yet.\nEveryone should send /setlang.")
        return

    lang_lines = "\n".join(
        f"  • {get_language_name(u['language'])} ({u['language']})" for u in users
    )
    await _reply(
        update.message,
        f"📊 <b>Group Translation Stats</b>\n\n"
        f"Members with language set: <b>{len(users)}</b>\n"
        f"Total translations: <b>{stats['total']:,}</b>\n\n"
        f"<b>Active languages:</b>\n{lang_lines}",
    )


# ── /enable & /disable ────────────────────────────────────────────────────────

async def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if chat.type == "private":
        return True
    admins = await context.bot.get_chat_administrators(chat.id)
    return any(a.user.id == user.id for a in admins)


async def cmd_enable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_admin(update, context):
        await _reply(update.message, "⛔ Only admins can use this command.")
        return
    await _db(context).enable_group(update.effective_chat.id)
    await _reply(update.message, f"✅ {BOT_NAME} translations <b>enabled</b>.")


async def cmd_disable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_admin(update, context):
        await _reply(update.message, "⛔ Only admins can use this command.")
        return
    await _db(context).disable_group(update.effective_chat.id)
    await _reply(update.message, f"⏸ {BOT_NAME} translations <b>paused</b>.")


# ── Callback query handler ────────────────────────────────────────────────────

async def callback_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data: str = query.data
    user = update.effective_user
    chat = update.effective_chat

    if data == "noop":
        return

    if data.startswith("lang_page:"):
        page = int(data.split(":")[1])
        await query.edit_message_reply_markup(reply_markup=language_main_menu(page=page))
        return

    if data.startswith("lang:"):
        code = data.split(":")[1]
        name = get_language_name(code)
        await query.edit_message_text(
            f"Set your language to <b>{name}</b>?",
            parse_mode=ParseMode.HTML,
            reply_markup=confirm_language(code, name),
        )
        return

    if data.startswith("confirm_lang:"):
        code = data.split(":")[1]
        name = get_language_name(code)
        db = _db(context)

        # Determine which chat this preference is for
        target_chat = context.user_data.get("pending_setlang_chat", chat.id)

        await db.set_user_language(user.id, target_chat, code)

        # If it was a group setting, mark the group active
        if target_chat != chat.id:
            await db.enable_group(target_chat)

        # Clear pending
        context.user_data.pop("pending_setlang_chat", None)

        await query.edit_message_text(
            f"✅ Language set to <b>{name}</b> ({code}).\n\n"
            "All messages in the group will now appear in your chosen language.",
            parse_mode=ParseMode.HTML,
        )
        return


# ── Core message translation ──────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Main translation flow (group messages only):
    1. Check group is enabled and has subscribers
    2. Delete the original message
    3. Detect source language
    4. Fan-out: translate to each unique target language concurrently
    5. Post one message per unique language in the group
       (each post is labeled with sender name + original text)
    6. Sender's original text is always preserved in the post header
    """
    message = update.effective_message
    chat = update.effective_chat
    sender = update.effective_user

    if not sender or chat.type not in ("group", "supergroup"):
        return

    text = message.text or message.caption
    if not text or len(text.strip()) < MIN_MESSAGE_LENGTH:
        return

    db = _db(context)

    if not await db.is_group_enabled(chat.id):
        return

    subscribers = await db.get_all_users_in_chat(chat.id)
    if not subscribers:
        return

    translator = get_translator()

    # Detect source language once
    _, src_lang = await translator.translate(text, "en")

    # Build map of target_lang → [user_ids]  (excluding sender if they have same lang)
    lang_to_users: dict[str, list[int]] = {}
    sender_lang: str | None = None

    for sub in subscribers:
        if sub["user_id"] == sender.id:
            sender_lang = sub["language"]
            continue
        tgt = sub["language"]
        if tgt == src_lang:
            continue   # already in their language, no translation needed
        lang_to_users.setdefault(tgt, []).append(sub["user_id"])

    # Always include sender's original language group (they see their own text)
    # We'll post one message for the source language too if no subscribers share it

    # Gather unique target languages
    unique_targets = list(lang_to_users.keys())

    if not unique_targets and sender_lang == src_lang:
        # Nobody needs translation, nothing to do
        return

    # Delete the original message (best-effort — bot needs delete permission)
    original_text = text
    sender_display = sender.full_name or sender.first_name or "Someone"
    sender_mention = f'<a href="tg://user?id={sender.id}">{sender_display}</a>'

    try:
        await message.delete()
    except BadRequest as e:
        logger.warning("Could not delete original message: %s", e)
        # If we can't delete, we still post translations but note the source

    # Translate all unique targets concurrently
    async def do_translate(tgt_lang: str) -> tuple[str, str]:
        translated, _ = await translator.translate(original_text, tgt_lang, src_lang)
        return tgt_lang, translated

    results = await asyncio.gather(
        *[do_translate(lang) for lang in unique_targets],
        return_exceptions=True,
    )

    translation_map: dict[str, str] = {}
    for r in results:
        if isinstance(r, Exception):
            logger.error("Translation failed: %s", r)
            continue
        tgt_lang, translated = r
        translation_map[tgt_lang] = translated

    # Post one message per unique target language in the group
    for tgt_lang, translated in translation_map.items():
        tgt_name = get_language_name(tgt_lang)
        src_name = get_language_name(src_lang)

        body = (
            f"💬 {sender_mention} <i>({src_name} → {tgt_name})</i>\n"
            f"{'─' * 28}\n"
            f"{translated}"
        )

        if SHOW_ORIGINAL:
            body += f"\n\n<i>📝 Original: {original_text}</i>"

        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=body,
                parse_mode=ParseMode.HTML,
            )
            await db.log_translation(
                chat_id=chat.id,
                user_id=sender.id,
                src_lang=src_lang,
                tgt_lang=tgt_lang,
                char_count=len(original_text),
            )
        except Exception as exc:
            logger.error("Failed posting translation to group: %s", exc)

    # If the sender's language differs from all target langs, also post their version
    # (so they see their own message in the chat)
    if sender_lang and sender_lang not in translation_map:
        if sender_lang == src_lang:
            # Post original for the sender
            body = (
                f"💬 {sender_mention}\n"
                f"{'─' * 28}\n"
                f"{original_text}"
            )
        else:
            # Translate for sender too
            translated_for_sender, _ = await translator.translate(
                original_text, sender_lang, src_lang
            )
            body = (
                f"💬 {sender_mention} <i>({src_name} → {get_language_name(sender_lang)})</i>\n"
                f"{'─' * 28}\n"
                f"{translated_for_sender}"
            )
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=body,
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            logger.error("Failed posting sender version: %s", exc)


# ── Bot added to group ────────────────────────────────────────────────────────

async def handle_my_chat_member(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    result = update.my_chat_member
    chat = result.chat
    new_status = result.new_chat_member.status
    bot = context.bot

    if new_status in ("member", "administrator") and chat.type in ("group", "supergroup"):
        await _db(context).enable_group(chat.id)
        try:
            deep_link = f"https://t.me/{bot.username}?start=setlang_{chat.id}"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔒 Set my language privately →", url=deep_link)
            ]])
            await bot.send_message(
                chat_id=chat.id,
                text=(
                    f"👋 Hi! I'm <b>{BOT_NAME}</b> — your group translation assistant.\n\n"
                    "I translate every message so each member reads the chat in their own language.\n\n"
                    "📌 <b>Each member:</b> click below to privately set your preferred language.\n"
                    "⚠️ <b>Admin:</b> please give me <b>Delete Messages</b> permission so I can replace messages with translations."
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
        except Exception:
            pass


# ── Registration ──────────────────────────────────────────────────────────────

def register_all_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("setlang", cmd_setlang))
    app.add_handler(CommandHandler("mylang", cmd_mylang))
    app.add_handler(CommandHandler("groupstats", cmd_groupstats))
    app.add_handler(CommandHandler("enable", cmd_enable))
    app.add_handler(CommandHandler("disable", cmd_disable))

    app.add_handler(CallbackQueryHandler(callback_language))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    app.add_handler(
        ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)
    )