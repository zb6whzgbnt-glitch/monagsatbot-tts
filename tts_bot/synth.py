from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from . import edge_synth, fish_synth, gemini_tts

log = logging.getLogger("tts_bot.synth")

ProgressCb = Callable[[str], Awaitable[None]]


@dataclass
class SynthResult:
    audio: bytes
    engine: str  # "gemini" | "edge" | "fish"


async def synthesize_full(
    text: str,
    gender: str,
    rate: str,
    *,
    engine: str,
    on_progress: ProgressCb | None = None,
) -> SynthResult:
    """Synthesize with the explicitly chosen engine only.

    No silent cross-engine fallback: if the chosen engine fails, raise.
    """
    chosen = (engine or "").strip().lower()
    if chosen not in ("gemini", "edge", "fish"):
        raise ValueError(f"unknown engine: {engine!r}")

    if chosen == "gemini":
        audio = await gemini_tts.synthesize_full(
            text, gender, rate, on_progress=on_progress
        )
        if not audio:
            raise RuntimeError("empty gemini audio")
        log.info(
            "gemini ok gender=%s rate=%s chars=%s bytes=%s",
            gender,
            rate,
            len(text),
            len(audio),
        )
        return SynthResult(audio=audio, engine="gemini")

    if chosen == "fish":
        audio = await fish_synth.synthesize_full(
            text, gender, rate, on_progress=on_progress
        )
        if not audio:
            raise RuntimeError("empty fish audio")
        log.info(
            "fish ok gender=%s rate=%s chars=%s bytes=%s",
            gender,
            rate,
            len(text),
            len(audio),
        )
        return SynthResult(audio=audio, engine="fish")

    audio = await edge_synth.synthesize_full(
        text, gender, rate, on_progress=on_progress
    )
    if not audio:
        raise RuntimeError("empty edge audio")
    log.info(
        "edge ok gender=%s rate=%s chars=%s bytes=%s",
        gender,
        rate,
        len(text),
        len(audio),
    )
    return SynthResult(audio=audio, engine="edge")
