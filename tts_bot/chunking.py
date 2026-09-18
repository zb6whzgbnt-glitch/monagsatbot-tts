from __future__ import annotations

import re


def split_text(text: str, min_chars: int = 800, max_chars: int = 1200) -> list[str]:
    """Split long text into chunks preferring paragraph/sentence boundaries."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining.strip())
            break

        window = remaining[:max_chars]
        cut = -1

        # Prefer paragraph break in the latter half of the window
        para = window.rfind("\n\n")
        if para >= min_chars:
            cut = para

        if cut < 0:
            # Sentence-ish: Arabic / Latin punctuation
            for m in re.finditer(r"[.!?؟。…]\s+", window):
                if m.end() >= min_chars:
                    cut = m.end()
            # Keep the last valid sentence end in range
            if cut < min_chars:
                cut = -1
                for m in re.finditer(r"[.!?؟。…]\s+", window):
                    if min_chars <= m.end() <= max_chars:
                        cut = m.end()

        if cut < 0:
            nl = window.rfind("\n")
            if nl >= min_chars:
                cut = nl

        if cut < 0:
            sp = window.rfind(" ")
            if sp >= min_chars:
                cut = sp

        if cut < 0:
            cut = max_chars

        piece = remaining[:cut].strip()
        if piece:
            chunks.append(piece)
        remaining = remaining[cut:].lstrip()

    return [c for c in chunks if c]
