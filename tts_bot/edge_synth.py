from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path

import edge_tts

from .chunking import split_text
from .config import (
    TTS_CHUNK_MAX,
    TTS_CHUNK_MIN,
    VOICE_FEMALE,
    VOICE_FEMALE_FALLBACK,
    VOICE_MALE,
    VOICE_MALE_FALLBACK,
)

log = logging.getLogger("tts_bot.edge")

ProgressCb = Callable[[str], Awaitable[None]]


def voices_for_gender(gender: str) -> tuple[str, str]:
    g = (gender or "").lower()
    if g in ("female", "f", "امرأة", "woman"):
        return VOICE_FEMALE, VOICE_FEMALE_FALLBACK
    return VOICE_MALE, VOICE_MALE_FALLBACK


async def _synthesize_one(text: str, voice: str, rate: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
    await communicate.save(str(out_path))


async def synthesize_chunk(
    text: str, primary: str, fallback: str, rate: str, out_path: Path
) -> None:
    try:
        await _synthesize_one(text, primary, rate, out_path)
    except Exception as exc:
        log.warning(
            "primary voice %s failed: %s; trying fallback %s",
            primary,
            exc,
            fallback,
        )
        await _synthesize_one(text, fallback, rate, out_path)


def _concat_mp3(paths: list[Path], out_path: Path) -> None:
    if len(paths) == 1:
        out_path.write_bytes(paths[0].read_bytes())
        return
    with tempfile.TemporaryDirectory() as td:
        list_file = Path(td) / "list.txt"
        lines = []
        for p in paths:
            escaped = str(p).replace("'", "'\\''")
            lines.append(f"file '{escaped}'")
        list_file.write_text("\n".join(lines), encoding="utf-8")
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(out_path),
        ]
        subprocess.run(cmd, check=True)


async def synthesize_full(
    text: str,
    gender: str,
    rate: str,
    *,
    on_progress: ProgressCb | None = None,
) -> bytes:
    """Synthesize full text; return a single MP3 (merged if chunked)."""
    primary, fallback = voices_for_gender(gender)
    chunks = split_text(text, TTS_CHUNK_MIN, TTS_CHUNK_MAX)
    if not chunks:
        raise ValueError("empty text")

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        part_paths: list[Path] = []
        for i, chunk in enumerate(chunks):
            if on_progress and i == 0:
                await on_progress("convert")
            part = td_path / f"part_{i:04d}.mp3"
            await synthesize_chunk(chunk, primary, fallback, rate, part)
            if not part.exists() or part.stat().st_size == 0:
                raise RuntimeError(f"empty audio for chunk {i}")
            part_paths.append(part)

        out = td_path / "full.mp3"
        if len(part_paths) > 1:
            if on_progress:
                await on_progress("merge")
            await asyncio.to_thread(_concat_mp3, part_paths, out)
        else:
            out.write_bytes(part_paths[0].read_bytes())

        data = out.read_bytes()
        if not data:
            raise RuntimeError("empty merged audio")
        return data
