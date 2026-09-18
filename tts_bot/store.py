from __future__ import annotations

import json
import sqlite3
from typing import Any

from .config import DATA_DIR, DEFAULT_VOICE

DB_PATH = DATA_DIR / "bot.sqlite"

DEFAULTS: dict[str, Any] = {
    "voice": DEFAULT_VOICE,
    "tone": "محايد",
    "speed": "عادي",
    "style": "راوي",
    "dialect": "فصحى واضحة",
    "formality": "عادي",
    "custom_notes": "",
    "presets": {},
}


def init() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                data TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _merge(raw: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(DEFAULTS)
    out["presets"] = {}
    if raw:
        for k, v in raw.items():
            if k == "presets" and isinstance(v, dict):
                out["presets"] = v
            elif k in DEFAULTS and k != "presets":
                out[k] = v
    return out


def get_settings(user_id: int) -> dict[str, Any]:
    init()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT data FROM user_settings WHERE user_id=?", (user_id,)
        ).fetchone()
    if not row:
        return _merge(None)
    try:
        return _merge(json.loads(row[0]))
    except Exception:
        return _merge(None)


def save_settings(user_id: int, settings: dict[str, Any]) -> dict[str, Any]:
    init()
    merged = _merge(settings)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO user_settings(user_id, data) VALUES(?,?)\n"
            "ON CONFLICT(user_id) DO UPDATE SET data=excluded.data",
            (user_id, json.dumps(merged, ensure_ascii=False)),
        )
        conn.commit()
    return merged


def update_field(user_id: int, key: str, value: Any) -> dict[str, Any]:
    s = get_settings(user_id)
    s[key] = value
    return save_settings(user_id, s)


def reset_settings(user_id: int) -> dict[str, Any]:
    return save_settings(user_id, dict(DEFAULTS))


def save_preset(user_id: int, slot: str) -> dict[str, Any]:
    s = get_settings(user_id)
    presets = dict(s.get("presets") or {})
    presets[slot] = {
        k: s.get(k)
        for k in ("voice", "tone", "speed", "style", "dialect", "formality", "custom_notes")
    }
    s["presets"] = presets
    return save_settings(user_id, s)


def load_preset(user_id: int, slot: str) -> dict[str, Any] | None:
    s = get_settings(user_id)
    presets = s.get("presets") or {}
    snap = presets.get(slot)
    if not isinstance(snap, dict):
        return None
    for k, v in snap.items():
        s[k] = v
    return save_settings(user_id, s)


def summary_text(s: dict[str, Any]) -> str:
    notes = (s.get("custom_notes") or "").strip()
    notes_line = notes if notes else "—"
    if len(notes_line) > 80:
        notes_line = notes_line[:77] + "…"
    return (
        f"🎙 الشخصية: {s.get('voice')}\n"
        f"🎭 النبرة: {s.get('tone')}\n"
        f"⏱ السرعة: {s.get('speed')}\n"
        f"🎬 الأسلوب: {s.get('style')}\n"
        f"🗣 اللهجة: {s.get('dialect')}\n"
        f"👔 الرسمية: {s.get('formality')}\n"
        f"📝 تعليمات: {notes_line}"
    )
