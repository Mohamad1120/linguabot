"""
src/database.py
Async SQLite-backed persistence for user language preferences.
Uses aiosqlite for non-blocking I/O so the bot loop is never stalled.
"""

import logging
import aiosqlite
from config.settings import DATABASE_PATH

logger = logging.getLogger(__name__)


class Database:
    """Thin async wrapper around SQLite."""

    def __init__(self, path: str = DATABASE_PATH):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def init(self) -> None:
        """Open the connection and create tables if they don't exist."""
        import os
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)

        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._create_tables()
        logger.info("SQLite connected: %s", self.path)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    # ── Schema ────────────────────────────────────────────────────────────────

    async def _create_tables(self) -> None:
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id     INTEGER NOT NULL,
                chat_id     INTEGER NOT NULL,
                language    TEXT    NOT NULL DEFAULT 'en',
                updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, chat_id)
            );

            CREATE TABLE IF NOT EXISTS group_settings (
                chat_id         INTEGER PRIMARY KEY,
                enabled         INTEGER NOT NULL DEFAULT 1,
                added_at        TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS translation_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id         INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                src_lang        TEXT,
                tgt_lang        TEXT    NOT NULL,
                char_count      INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
            );
        """)
        await self._conn.commit()

    # ── User preferences ──────────────────────────────────────────────────────

    async def get_user_language(self, user_id: int, chat_id: int) -> str | None:
        """Return the user's preferred language for this chat, or None."""
        async with self._conn.execute(
            "SELECT language FROM user_preferences WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as cur:
            row = await cur.fetchone()
            return row["language"] if row else None

    async def set_user_language(
        self, user_id: int, chat_id: int, language: str
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO user_preferences (user_id, chat_id, language)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, chat_id) DO UPDATE
                SET language=excluded.language,
                    updated_at=datetime('now')
            """,
            (user_id, chat_id, language),
        )
        await self._conn.commit()

    async def get_all_users_in_chat(self, chat_id: int) -> list[dict]:
        """Return all (user_id, language) pairs registered in a chat."""
        async with self._conn.execute(
            "SELECT user_id, language FROM user_preferences WHERE chat_id=?",
            (chat_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [{"user_id": r["user_id"], "language": r["language"]} for r in rows]

    async def remove_user_preference(self, user_id: int, chat_id: int) -> None:
        await self._conn.execute(
            "DELETE FROM user_preferences WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        )
        await self._conn.commit()

    # ── Group settings ────────────────────────────────────────────────────────

    async def enable_group(self, chat_id: int) -> None:
        await self._conn.execute(
            """
            INSERT INTO group_settings (chat_id, enabled)
            VALUES (?, 1)
            ON CONFLICT(chat_id) DO UPDATE SET enabled=1
            """,
            (chat_id,),
        )
        await self._conn.commit()

    async def disable_group(self, chat_id: int) -> None:
        await self._conn.execute(
            "UPDATE group_settings SET enabled=0 WHERE chat_id=?",
            (chat_id,),
        )
        await self._conn.commit()

    async def is_group_enabled(self, chat_id: int) -> bool:
        async with self._conn.execute(
            "SELECT enabled FROM group_settings WHERE chat_id=?",
            (chat_id,),
        ) as cur:
            row = await cur.fetchone()
            return bool(row["enabled"]) if row else False

    # ── Logging ───────────────────────────────────────────────────────────────

    async def log_translation(
        self,
        chat_id: int,
        user_id: int,
        src_lang: str | None,
        tgt_lang: str,
        char_count: int,
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO translation_log (chat_id, user_id, src_lang, tgt_lang, char_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (chat_id, user_id, src_lang, tgt_lang, char_count),
        )
        await self._conn.commit()

    async def get_stats(self, chat_id: int) -> dict:
        async with self._conn.execute(
            """
            SELECT COUNT(*) as total,
                   COUNT(DISTINCT user_id) as users,
                   SUM(char_count) as chars
            FROM translation_log WHERE chat_id=?
            """,
            (chat_id,),
        ) as cur:
            row = await cur.fetchone()
            return {
                "total": row["total"] or 0,
                "users": row["users"] or 0,
                "chars": row["chars"] or 0,
            }
