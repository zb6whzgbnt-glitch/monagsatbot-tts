from __future__ import annotations

import re

# Leading number marker: Western or Arabic-Indic digits, then . ) - ، or :
_NUMBER_START = re.compile(
    r"(?m)^\s*([0-9]+|[٠-٩]+)\s*[.\)\-\u060C:]\s+"
)


def _strip_marker(block: str) -> str | None:
    """If block starts with a number marker, return text after it; else None."""
    m = _NUMBER_START.match(block)
    if not m:
        return None
    return block[m.end() :].strip()


def _parse_blank_line_blocks(text: str) -> list[str] | None:
    """Split on blank lines; every non-empty block must be numbered."""
    parts = re.split(r"\n\s*\n+", text.strip())
    blocks = [p.strip() for p in parts if p.strip()]
    if len(blocks) < 2:
        return None
    prompts: list[str] = []
    for block in blocks:
        stripped = _strip_marker(block)
        if stripped is None or not stripped:
            return None
        prompts.append(stripped)
    return prompts if len(prompts) >= 2 else None


def _parse_line_starts(text: str) -> list[str] | None:
    """Treat every line that starts with a number marker as a new prompt."""
    text = text.strip()
    if not text:
        return None
    matches = list(_NUMBER_START.finditer(text))
    if len(matches) < 2:
        return None
    # First match should be at the start of the message (allow leading whitespace)
    if matches[0].start() != 0 and text[: matches[0].start()].strip():
        return None
    prompts: list[str] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if not body:
            return None
        prompts.append(body)
    return prompts if len(prompts) >= 2 else None


def _blank_line_block_count(text: str) -> int:
    parts = re.split(r"\n\s*\n+", text.strip())
    return len([p for p in parts if p.strip()])


def parse_numbered_prompts(text: str) -> list[str] | None:
    """Parse a batch of numbered prompts.

    Returns an ordered list of prompt texts (markers stripped), or None if the
    message is not a numbered batch (caller should treat as a single TTS).
    """
    if not text or not text.strip():
        return None
    parsed = _parse_blank_line_blocks(text)
    if parsed is not None:
        return parsed
    # Mixed blank-line blocks (some numbered, some not) are not a batch.
    if _blank_line_block_count(text) >= 2:
        return None
    return _parse_line_starts(text)
