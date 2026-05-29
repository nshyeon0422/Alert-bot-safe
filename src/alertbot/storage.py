from __future__ import annotations

import sqlite3
from typing import Optional

from .parser import ParsedItem


class Storage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    link TEXT,
                    content_hash TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_items_link ON items(link)")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_items_hash ON items(content_hash)"
            )
            conn.commit()

    def is_seen(self, item: ParsedItem) -> bool:
        query = "SELECT 1 FROM items WHERE content_hash = ?"
        params = (item.content_hash,)
        if item.link:
            query = "SELECT 1 FROM items WHERE link = ?"
            params = (item.link,)
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(query, params)
            return cur.fetchone() is not None

    def is_empty(self) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT 1 FROM items LIMIT 1")
            return cur.fetchone() is None

    def mark_seen(self, item: ParsedItem) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO items (title, link, content_hash) VALUES (?, ?, ?)",
                (item.title, item.link, item.content_hash),
            )
            conn.commit()

    def prune_keep_latest(self, limit: int) -> None:
        if limit <= 0:
            return
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                DELETE FROM items
                WHERE id NOT IN (
                    SELECT id FROM items ORDER BY id DESC LIMIT ?
                )
                """,
                (limit,),
            )
            conn.commit()
