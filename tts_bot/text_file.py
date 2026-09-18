from __future__ import annotations

import logging

from .pdf_extract import clean_extracted_text, is_meaningful_text

log = logging.getLogger("tts_bot.txt")

_UTF8_BOM = b"\xef\xbb\xbf"


class TextFileError(Exception):
    """Text file could not be decoded."""


def decode_text_bytes(data: bytes) -> str:
    """Decode file bytes: utf-8, then cp1256 / windows-1256, then latin-1.

    Strips a UTF-8 BOM if present. latin-1 uses replacement so it always
    produces a string. Returns cleaned text (may be empty).
    """
    if not data:
        return ""

    if data.startswith(_UTF8_BOM):
        data = data[len(_UTF8_BOM) :]

    text: str | None = None
    used = "latin-1"
    for encoding in ("utf-8", "cp1256", "windows-1256"):
        try:
            text = data.decode(encoding)
            used = encoding
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = data.decode("latin-1", errors="replace")

    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")

    cleaned = clean_extracted_text(text)
    log.info("txt decoded via %s chars=%s", used, len(cleaned))
    return cleaned


def extract_txt_text(data: bytes) -> str:
    """Decode and clean a .txt payload. Empty string if no meaningful text."""
    cleaned = decode_text_bytes(data)
    if not is_meaningful_text(cleaned):
        return ""
    return cleaned
