from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .config import DATA_DIR

DB_PATH = DATA_DIR / "bot.sqlite"


def init() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def list_titles(limit: int = 200) -> list[str]:
    """Return recent article titles (newest first), for anti-repeat."""
    init()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT title FROM articles ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [r[0] for r in rows if r and r[0]]


def add_title(title: str) -> None:
    init()
    title = (title or "").strip()
    if not title:
        return
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO articles(title, created_at) VALUES(?, ?)",
            (title, now),
        )
        conn.commit()
