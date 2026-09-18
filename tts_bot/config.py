from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

# Prefer TELEGRAM_BOT_TOKEN; also accept BOT_TOKEN.
TELEGRAM_BOT_TOKEN = (
    os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    or os.environ.get("BOT_TOKEN", "").strip()
)

DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Gemini TTS (primary) ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
# Primary / fallback Gemini TTS models (Generate Content API)
TTS_MODEL = os.environ.get("TTS_MODEL", "gemini-2.5-flash-preview-tts").strip()
TTS_FALLBACK_MODEL = os.environ.get(
    "TTS_FALLBACK_MODEL", "gemini-2.5-pro-preview-tts"
).strip()
# Prebuilt Gemini voices (Arabic-capable; auto language detect).
# Male: Fenrir (excitable) — alternatives: Charon, Puck, Orus, Alnilam
# Female: Aoede (breezy narration) — alternatives: Kore, Leda, Achernar, Despina
GEMINI_VOICE_MALE = os.environ.get("GEMINI_VOICE_MALE", "Fenrir").strip() or "Fenrir"
GEMINI_VOICE_FEMALE = (
    os.environ.get("GEMINI_VOICE_FEMALE", "Aoede").strip() or "Aoede"
)
GEMINI_TTS_TIMEOUT_SEC = float(os.environ.get("GEMINI_TTS_TIMEOUT_SEC", "90"))

# --- Fish Audio TTS ---
FISH_API_KEY = os.environ.get("FISH_API_KEY", "").strip()
FISH_TTS_MODEL = (
    os.environ.get("FISH_TTS_MODEL", "s2.1-pro-free").strip() or "s2.1-pro-free"
)
# Public Arabic-capable library voices (overridable). Empty = Fish auto voice.
# Male: "Arabic - العربية" narration. Female: "صوت أنثوي عربي".
FISH_VOICE_MALE = os.environ.get(
    "FISH_VOICE_MALE", "55542ca9d06d4111977d1f06c905a3a5"
).strip()
FISH_VOICE_FEMALE = os.environ.get(
    "FISH_VOICE_FEMALE", "f2acd2bec2db4cf1827172299c2900ef"
).strip()
FISH_TTS_TIMEOUT_SEC = float(os.environ.get("FISH_TTS_TIMEOUT_SEC", "120"))

# Microsoft Edge neural voices (Arabic) — fallback path

VOICE_FEMALE = os.environ.get("EDGE_VOICE_FEMALE", "ar-SA-ZariyahNeural").strip()
VOICE_FEMALE_FALLBACK = os.environ.get(
    "EDGE_VOICE_FEMALE_FALLBACK", "ar-EG-SalmaNeural"
).strip()
VOICE_MALE = os.environ.get("EDGE_VOICE_MALE", "ar-SA-HamedNeural").strip()
VOICE_MALE_FALLBACK = os.environ.get(
    "EDGE_VOICE_MALE_FALLBACK", "ar-EG-ShakirNeural"
).strip()

# Chunk size for long text (~800–1200 chars)
TTS_CHUNK_MIN = int(os.environ.get("TTS_CHUNK_MIN", "800"))
TTS_CHUNK_MAX = int(os.environ.get("TTS_CHUNK_MAX", "1200"))

# Pending selection expiry (seconds)
PENDING_TTL_SEC = int(os.environ.get("PENDING_TTL_SEC", "600"))

# Private bot: comma-separated Telegram user IDs allowed to use TTS
def _parse_allowed_ids(raw: str) -> frozenset[int]:
    out: set[int] = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            pass
    return frozenset(out)


ALLOWED_USER_IDS: frozenset[int] = _parse_allowed_ids(
    os.environ.get("ALLOWED_USER_IDS", "8415608677")
)

# PDF / plain-text document support
PDF_MAX_BYTES = int(os.environ.get("PDF_MAX_BYTES", str(20 * 1024 * 1024)))
PDF_LONG_WARN_CHARS = int(os.environ.get("PDF_LONG_WARN_CHARS", "8000"))
TXT_MAX_BYTES = int(os.environ.get("TXT_MAX_BYTES", str(20 * 1024 * 1024)))

# Speed label -> edge-tts rate string
SPEED_RATES: dict[str, str] = {
    "0.75": "-25%",
    "1.0": "+0%",
    "1.25": "+25%",
    "1.5": "+50%",
}

# Edge rate string -> ffmpeg atempo (Gemini has no Edge-style rate)
RATE_TO_ATEMPO: dict[str, float] = {
    "-25%": 0.75,
    "+0%": 1.0,
    "+25%": 1.25,
    "+50%": 1.5,
}

# --- Cohere (optional article generation module) ---
COHERE_API_KEY = os.environ.get("COHERE_API_KEY", "").strip()
COHERE_MODEL = (
    os.environ.get("COHERE_MODEL", "command-a-03-2025").strip() or "command-a-03-2025"
)

# --- Webhook / Render ---
# Full public webhook base or full URL. If unset, built from RENDER_EXTERNAL_HOSTNAME.
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip()
WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "telegram").strip() or "telegram"
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "").strip()
# Render sets RENDER=true and RENDER_EXTERNAL_HOSTNAME automatically.
RENDER = os.environ.get("RENDER", "").strip().lower() in ("1", "true", "yes")
PORT = int(os.environ.get("PORT", "8080"))


def webhook_mode_enabled() -> bool:
    """True when running behind a public HTTPS URL (Render / explicit WEBHOOK_URL)."""
    if WEBHOOK_URL:
        return True
    if os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip():
        return True
    if RENDER:
        return True
    return False
