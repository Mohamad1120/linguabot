"""
src/handlers.py
All Telegram update handlers wired together.

Architecture:
  /start /help      → command_handlers.py logic (inline here for simplicity)
  /setlang          → opens the language-selection keyboard
  /mystats          → per-user stats in this chat
  /groupstats       → group-wide stats
  /enable /disable  → admin controls for the group
  message listener  → translates every text message for subscribed users
  callback_query    → handles keyboard interactions
"""

import asyncio
import logging

from telegram import Update, Message
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config.settings import MIN_MESSAGE_LENGTH, SHOW_ORIGINAL
from .database import Database
from .keyboards import language_main_menu, confirm_language
from .languages import get_language_name, is_valid_language
from .translator import get_translator

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["db"]


async def _reply(message: Message, text: str, **kwargs) -> None:
    await message.reply_text(text, parse_mode="HTML", **kwargs)


# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    is_group = chat.type in ("group", "supergroup")

    welcome = (
        f"👋 Hello, <b>{user.first_name}</b>!\n\n"
        "I'm <b>LinguaBot</b> — your real-time translation companion.\n\n"
    )
    if is_group:
        welcome += (
            "📌 <b>How it works in this group:</b>\n"
            "• Use /setlang to choose <i>your</i> preferred language.\n"
            "• Every message in the group will be automatically translated "
            "into your chosen language and sent to you privately.\n\n"
            "💡 Each member can pick a <i>different</i> language independently!"
        )
    else:
        welcome += (
            "Add me to a group and I'll translate all messages for each member "
            "in their own preferred language.\n\n"
            "Use /setlang to set your language preference."
        )
    await _reply(update.message, welcome)


# ── /help ─────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(
        update.message,
        "<b>🌐 LinguaBot — Commands</b>\n\n"
        "/start — Welcome message\n"
        "/setlang — Set your preferred language\n"
        "/mylang — Show your current language setting\n"
        "/mystats — Your translation stats in this chat\n"
        "/groupstats — Group-wide translation stats\n"
        "/enable — Enable translations in this group (admin)\n"
        "/disable — Pause translations in this group (admin)\n"
        "/help — Show this message\n\n"
        "<i>Tip: Use /setlang in the group to set your language without leaving the chat.</i>",
    )


# ── /setlang ──────────────────────────────────────────────────────────────────

async def cmd_setlang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # If a code was passed inline: /setlang en
    args = context.args
    if args:
        code = args[0].lower()
        if is_valid_language(code):
            await _apply_language(update, context, code)
            return
        else:
            await _reply(
                update.message,
                f"❌ Unknown language code <code>{code}</code>.\n"
                "Please choose from the menu below or use a valid BCP-47 code.",
            )

    keyboard = language_main_menu(page=0)
    await _reply(
        update.message,
        "🌍 <b>Choose your preferred language:</b>\n"
        "All messages in this chat will be translated to your selection.",
        reply_markup=keyboard,
    )


async def _apply_language(
    update: Update, context: ContextTypes.DEFAULT_TYPE, code: str
) -> None:
    user = update.effective_user
    chat = update.effective_chat
    db = _db(context)
    await db.set_user_language(user.id, chat.id, code)
    # Ensure group is registered as active
    if chat.type in ("group", "supergroup"):
        await db.enable_group(chat.id)

    name = get_language_name(code)
    await _reply(
        update.message or update.callback_query.message,
        f"✅ Language set to <b>{name}</b> ({code}).\n"
        "All new messages in this chat will be translated for you.",
    )


# ── /mylang ───────────────────────────────────────────────────────────────────

async def cmd_mylang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _db(context)
    user = update.effective_user
    chat = update.effective_chat
    code = await db.get_user_language(user.id, chat.id)
    if code:
        name = get_language_name(code)
        await _reply(update.message, f"🗣 Your current language: <b>{name}</b> ({code})")
    else:
        await _reply(
            update.message,
            "You haven't set a language yet.\nUse /setlang to choose one.",
        )


# ── /mystats ──────────────────────────────────────────────────────────────────

async def cmd_mystats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _db(context)
    chat = update.effective_chat
    user = update.effective_user
    # Reuse group stats for now (per-user stat query can be added to DB later)
    stats = await db.get_stats(chat.id)
    code = await db.get_user_language(user.id, chat.id) or "not set"
    name = get_language_name(code) if code != "not set" else "not set"
    await _reply(
        update.message,
        f"📊 <b>Your stats in this chat</b>\n\n"
        f"Preferred language: <b>{name}</b>\n"
        f"Group total translations: <b>{stats['total']:,}</b>\n"
        f"Group total characters: <b>{stats['chars']:,}</b>",
    )


# ── /groupstats ───────────────────────────────────────────────────────────────

async def cmd_groupstats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _db(context)
    chat = update.effective_chat
    stats = await db.get_stats(chat.id)
    users = await db.get_all_users_in_chat(chat.id)
    lang_summary = ", ".join(
        f"{get_language_name(u['language'])} ({u['language']})" for u in users[:10]
    )
    await _reply(
        update.message,
        f"📊 <b>Group Translation Stats</b>\n\n"
        f"Subscribed members: <b>{len(users)}</b>\n"
        f"Total translations: <b>{stats['total']:,}</b>\n"
        f"Total characters: <b>{stats['chars']:,}</b>\n\n"
        f"<b>Active languages:</b>\n{lang_summary or 'none yet'}",
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
        await _reply(update.message, "⛔ Only group admins can use this command.")
        return
    await _db(context).enable_group(update.effective_chat.id)
    await _reply(update.message, "✅ LinguaBot translations are <b>enabled</b> in this group.")


async def cmd_disable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_admin(update, context):
        await _reply(update.message, "⛔ Only group admins can use this command.")
        return
    await _db(context).disable_group(update.effective_chat.id)
    await _reply(update.message, "⏸ LinguaBot translations are <b>paused</b> in this group.")


# ── Callback query handler (inline keyboards) ─────────────────────────────────

async def callback_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data: str = query.data

    if data == "noop":
        return

    if data.startswith("lang_page:"):
        page = int(data.split(":")[1])
        kb = language_main_menu(page=page)
        await query.edit_message_reply_markup(reply_markup=kb)
        return

    if data.startswith("lang:"):
        code = data.split(":")[1]
        name = get_language_name(code)
        kb = confirm_language(code, name)
        await query.edit_message_text(
            f"🌐 Set your language to <b>{name}</b>?",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return

    if data.startswith("confirm_lang:"):
        code = data.split(":")[1]
        name = get_language_name(code)
        db = _db(context)
        user = update.effective_user
        chat = update.effective_chat
        await db.set_user_language(user.id, chat.id, code)
        if chat.type in ("group", "supergroup"):
            await db.enable_group(chat.id)
        await query.edit_message_text(
            f"✅ Done! Your language is now <b>{name}</b> ({code}).\n"
            "Incoming messages in this chat will be translated for you.",
            parse_mode="HTML",
        )
        return


# ── Message translation handler ───────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    sender = update.effective_user

    # Only in groups
    if chat.type not in ("group", "supergroup"):
        return

    text = message.text or message.caption
    if not text or len(text) < MIN_MESSAGE_LENGTH:
        return

    db = _db(context)

    # Is the bot enabled for this group?
    if not await db.is_group_enabled(chat.id):
        return

    # Get all subscribers in this chat
    subscribers = await db.get_all_users_in_chat(chat.id)
    if not subscribers:
        return

    translator = get_translator()

    # Detect source language once for the whole message
    _, src_lang = await translator.translate(text, "en")

    # Fan out translations concurrently
    tasks = []
    for sub in subscribers:
        if sub["user_id"] == sender.id:
            continue   # don't send back to the original author
        if sub["language"] == src_lang:
            continue   # already in the right language — skip

        tasks.append(
            _send_translation(
                context=context,
                db=db,
                chat_id=chat.id,
                recipient_id=sub["user_id"],
                sender=sender,
                original_text=text,
                src_lang=src_lang,
                tgt_lang=sub["language"],
                translator=translator,
            )
        )

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _send_translation(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    db: Database,
    chat_id: int,
    recipient_id: int,
    sender,
    original_text: str,
    src_lang: str,
    tgt_lang: str,
    translator,
) -> None:
    try:
        translated, _ = await translator.translate(original_text, tgt_lang, src_lang)

        src_name = get_language_name(src_lang)
        tgt_name = get_language_name(tgt_lang)
        sender_name = sender.full_name or sender.first_name

        body = (
            f"💬 <b>{sender_name}</b> <i>({src_name} → {tgt_name})</i>\n\n"
            f"{translated}"
        )
        if SHOW_ORIGINAL:
            body += f"\n\n<i>Original:</i> {original_text}"

        await context.bot.send_message(
            chat_id=recipient_id,
            text=body,
            parse_mode="HTML",
        )

        await db.log_translation(
            chat_id=chat_id,
            user_id=recipient_id,
            src_lang=src_lang,
            tgt_lang=tgt_lang,
            char_count=len(original_text),
        )

    except Exception as exc:
        logger.warning(
            "Failed to send translation to user %s: %s", recipient_id, exc
        )


# ── Bot added to group ────────────────────────────────────────────────────────

async def handle_my_chat_member(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    result = update.my_chat_member
    chat = result.chat
    new_status = result.new_chat_member.status

    if new_status in ("member", "administrator") and chat.type in (
        "group",
        "supergroup",
    ):
        db = _db(context)
        await db.enable_group(chat.id)
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    "👋 Hi everyone! I'm <b>LinguaBot</b>.\n\n"
                    "I'll translate messages in this group so everyone can read "
                    "them in their preferred language.\n\n"
                    "📌 Each member should use <b>/setlang</b> to choose their language.\n"
                    "Translations are delivered privately via direct message."
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass   # can't message yet — that's OK


# ── Registration ──────────────────────────────────────────────────────────────

def register_all_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("setlang", cmd_setlang))
    app.add_handler(CommandHandler("mylang", cmd_mylang))
    app.add_handler(CommandHandler("mystats", cmd_mystats))
    app.add_handler(CommandHandler("groupstats", cmd_groupstats))
    app.add_handler(CommandHandler("enable", cmd_enable))
    app.add_handler(CommandHandler("disable", cmd_disable))

    app.add_handler(CallbackQueryHandler(callback_language))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    app.add_handler(
        ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)
    )
