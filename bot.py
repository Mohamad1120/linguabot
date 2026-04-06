#!/usr/bin/env python3
"""
LinguaBot — Real-time Telegram Translation Bot
Entry point: starts the bot and initializes all components.
"""

import asyncio
import logging
from telegram.ext import Application
from config.settings import BOT_TOKEN, LOG_LEVEL
from src.handlers import register_all_handlers
from src.database import Database

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=getattr(logging, LOG_LEVEL, logging.INFO),
)
logger = logging.getLogger("linguabot")


async def post_init(application: Application) -> None:
    """Runs after the bot is initialized."""
    db = Database()
    await db.init()
    application.bot_data["db"] = db
    logger.info("Database initialized ✓")


def main() -> None:
    logger.info("Starting LinguaBot…")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .concurrent_updates(True)       # handle updates concurrently
        .build()
    )

    register_all_handlers(app)
    logger.info("All handlers registered ✓")

    app.run_polling(
        allowed_updates=["message", "callback_query", "my_chat_member"],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
