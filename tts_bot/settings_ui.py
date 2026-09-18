from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

from . import store
from .voices import DIALECTS, FORMALITIES, SPEEDS, STYLES, TONES, VOICES

BTN_SETTINGS = "\u2699\ufe0f \u0627\u0644\u0625\u0639\u062f\u0627\u062f\u0627\u062a"
BTN_PREVIEW = "\U0001f3a7 \u0645\u0639\u0627\u064a\u0646\u0629"


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_SETTINGS), KeyboardButton(BTN_PREVIEW)]],
        resize_keyboard=True,
        is_persistent=True,
    )


def main_settings_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("voice", callback_data="set:voices:0"), InlineKeyboardButton("tone", callback_data="set:menu:tone")],
        [InlineKeyboardButton("speed", callback_data="set:menu:speed"), InlineKeyboardButton("style", callback_data="set:menu:style")],
        [InlineKeyboardButton("dialect", callback_data="set:menu:dialect"), InlineKeyboardButton("formality", callback_data="set:menu:formality")],
        [InlineKeyboardButton("notes", callback_data="set:notes")],
        [InlineKeyboardButton("preview", callback_data="set:preview"), InlineKeyboardButton("refresh", callback_data="set:home")],
        [InlineKeyboardButton("save1", callback_data="set:psave:1"), InlineKeyboardButton("save2", callback_data="set:psave:2"), InlineKeyboardButton("save3", callback_data="set:psave:3")],
        [InlineKeyboardButton("load1", callback_data="set:pload:1"), InlineKeyboardButton("load2", callback_data="set:pload:2"), InlineKeyboardButton("load3", callback_data="set:pload:3")],
        [InlineKeyboardButton("reset", callback_data="set:reset")],
    ]
    # Arabic labels applied below for UX
    label = {
        "voice": "\U0001f3a4 \u0627\u0644\u0634\u062e\u0635\u064a\u0629",
        "tone": "\U0001f3ad \u0627\u0644\u0646\u0628\u0631\u0629",
        "speed": "\u23f1 \u0627\u0644\u0633\u0631\u0639\u0629",
        "style": "\U0001f3ac \u0627\u0644\u0623\u0633\u0644\u0648\u0628",
        "dialect": "\U0001f5e3 \u0627\u0644\u0644\u0647\u062c\u0629",
        "formality": "\U0001f454 \u0627\u0644\u0631\u0633\u0645\u064a\u0629",
        "notes": "\U0001f4dd \u062a\u0639\u0644\u064a\u0645\u0627\u062a \u0645\u062e\u0635\u0635\u0629",
        "preview": "\U0001f3a7 \u0645\u0639\u0627\u064a\u0646\u0629",
        "refresh": "\U0001f504 \u062a\u062d\u062f\u064a\u062b \u0627\u0644\u0639\u0631\u0636",
        "save1": "\U0001f4be \u062d\u0641\u0638 1",
        "save2": "\U0001f4be \u062d\u0641\u0638 2",
        "save3": "\U0001f4be \u062d\u0641\u0638 3",
        "load1": "\U0001f4c2 \u062a\u062d\u0645\u064a\u0644 1",
        "load2": "\U0001f4c2 \u062a\u062d\u0645\u064a\u0644 2",
        "load3": "\U0001f4c2 \u062a\u062d\u0645\u064a\u0644 3",
        "reset": "\u267b\ufe0f \u0625\u0639\u0627\u062f\u0629 \u0636\u0628\u0637",
    }
    out = []
    for row in rows:
        out.append([InlineKeyboardButton(label.get(b.text, b.text), callback_data=b.callback_data) for b in row])
    return InlineKeyboardMarkup(out)


def option_keyboard(kind: str, options: list[str], current: str) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for opt in options:
        mark = "\u2705 " if opt == current else ""
        row.append(InlineKeyboardButton(f"{mark}{opt}", callback_data=f"set:val:{kind}:{opt}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("\u2b05\ufe0f \u0631\u062c\u0648\u0639", callback_data="set:home")])
    return InlineKeyboardMarkup(rows)


def voices_keyboard(page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    total = len(VOICES)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    start = page * per_page
    chunk = VOICES[start:start + per_page]
    rows = []
    for name, style, gender in chunk:
        mark = "\u2640" if gender == "F" else "\u2642"
        rows.append([InlineKeyboardButton(f"{mark} {name} \u00b7 {style}", callback_data=f"set:voice:{name}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("\u25c0\ufe0f", callback_data=f"set:voices:{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="set:noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("\u25b6\ufe0f", callback_data=f"set:voices:{page+1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton("\u2b05\ufe0f \u0631\u062c\u0648\u0639", callback_data="set:home")])
    return InlineKeyboardMarkup(rows)


def settings_panel_text(user_id: int) -> str:
    s = store.get_settings(user_id)
    return (
        "\U0001f39b\ufe0f \u0644\u0648\u062d\u0629 \u062a\u062d\u0643\u0645 \u0627\u0644\u0635\u0648\u062a\n\n"
        + store.summary_text(s)
        + "\n\n\u0627\u062e\u062a\u0631 \u0645\u0646 \u0627\u0644\u0623\u0632\u0631\u0627\u0631 \u0644\u0636\u0628\u0637 \u0627\u0644\u0635\u0648\u062a \u0628\u062f\u0642\u0629\u060c \u062b\u0645 \u0623\u0631\u0633\u0644 \u0623\u064a \u0646\u0635 \u0644\u064a\u062a\u062d\u0648\u0644 \u062d\u0633\u0628 \u0625\u0639\u062f\u0627\u062f\u0627\u062a\u0643."
    )


OPTIONS = {
    "tone": TONES,
    "speed": SPEEDS,
    "style": STYLES,
    "dialect": DIALECTS,
    "formality": FORMALITIES,
}

TITLES = {
    "tone": "\U0001f3ad \u0627\u062e\u062a\u0631 \u0627\u0644\u0646\u0628\u0631\u0629",
    "speed": "\u23f1 \u0627\u062e\u062a\u0631 \u0627\u0644\u0633\u0631\u0639\u0629",
    "style": "\U0001f3ac \u0627\u062e\u062a\u0631 \u0627\u0644\u0623\u0633\u0644\u0648\u0628",
    "dialect": "\U0001f5e3 \u0627\u062e\u062a\u0631 \u0627\u0644\u0644\u0647\u062c\u0629",
    "formality": "\U0001f454 \u0627\u062e\u062a\u0631 \u062f\u0631\u062c\u0629 \u0627\u0644\u0631\u0633\u0645\u064a\u0629",
}
