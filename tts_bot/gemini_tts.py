from __future__ import annotations

import asyncio
import base64
import logging
import random
import subprocess
import tempfile
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path

from google import genai
from google.genai import types

from .chunking import split_text
from .config import (
    GEMINI_API_KEY,
    GEMINI_TTS_TIMEOUT_SEC,
    GEMINI_VOICE_FEMALE,
    GEMINI_VOICE_MALE,
    RATE_TO_ATEMPO,
    TTS_CHUNK_MAX,
    TTS_CHUNK_MIN,
    TTS_FALLBACK_MODEL,
    TTS_MODEL,
)

log = logging.getLogger("tts_bot.gemini")

ProgressCb = Callable[[str], Awaitable[None]]

_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY missing")
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def voice_for_gender(gender: str) -> str:
    g = (gender or "").lower()
    if g in ("female", "f", "امرأة", "woman"):
        return GEMINI_VOICE_FEMALE
    return GEMINI_VOICE_MALE


def _models() -> Iterable[str]:
    seen: set[str] = set()
    for m in (TTS_MODEL, TTS_FALLBACK_MODEL):
        m = (m or "").strip()
        if m and m not in seen:
            seen.add(m)
            yield m


def _call_with_retry(fn, tries: int = 4, base: float = 1.5):
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            msg = str(e)
            retryable = any(
                x in msg
                for x in (
                    "503",
                    "UNAVAILABLE",
                    "429",
                    "RESOURCE_EXHAUSTED",
                    "high demand",
                    "timed out",
                    "Timeout",
                    "500",
                    "INTERNAL",
                )
            )
            if not retryable or i == tries - 1:
                raise
            sleep_s = base * (2**i) + random.uniform(0, 1.0)
            log.warning(
                "gemini retry %s/%s after %.1fs: %s",
                i + 1,
                tries,
                sleep_s,
                msg[:160],
            )
            time_sleep(sleep_s)
    raise last  # type: ignore[misc]


def time_sleep(s: float) -> None:
    import time

    time.sleep(s)


def _extract_pcm(resp) -> tuple[bytes, int]:
    if not resp or not getattr(resp, "candidates", None):
        raise RuntimeError("empty tts response")
    parts = resp.candidates[0].content.parts
    raw = b""
    rate = 24000
    for part in parts:
        inline = getattr(part, "inline_data", None)
        if not inline or not inline.data:
            continue
        data = inline.data
        if isinstance(data, str):
            data = base64.b64decode(data)
        raw += data
        mime = getattr(inline, "mime_type", "") or ""
        if "rate=" in mime:
            try:
                rate = int(mime.split("rate=")[-1].split(";")[0])
            except ValueError:
                pass
    if not raw:
        raise RuntimeError("empty tts audio")
    return raw, rate


def _tts_prompt(text: str) -> str:
    """Clear TTS-only instruction so the model does not emit text tokens."""
    body = (text or "").strip()
    return (
        "Read the following text aloud exactly as written. "
        "Output audio only; do not add commentary.\n\n"
        + body
    )


def _synthesize_pcm_sync(text: str, voice_name: str) -> tuple[bytes, int]:
    body = (text or "").strip()
    if not body:
        raise ValueError("empty text")
    prompt = _tts_prompt(body)
    last_err: Exception | None = None

    for model in _models():

        def _gen(m=model):
            return client().models.generate_content(
                model=m,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_name
                            )
                        )
                    ),
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True
                    ),
                ),
            )

        try:
            log.info(
                "tts model=%s voice=%s chars=%s", model, voice_name, len(body)
            )
            resp = _call_with_retry(_gen, tries=4, base=1.5)
            return _extract_pcm(resp)
        except Exception as e:
            last_err = e
            log.warning("tts model %s failed: %s", model, str(e)[:200])
            continue
    raise RuntimeError(f"all tts models failed: {last_err}")


def _pcm_to_mp3(
    pcm: bytes, sample_rate: int, out_path: Path, atempo: float = 1.0
) -> None:
    """Write PCM s16le mono to MP3, optionally applying ffmpeg atempo."""
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "a.pcm"
        mid = Path(td) / "a.mp3"
        src.write_bytes(pcm)
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "s16le",
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-i",
            str(src),
        ]
        # atempo valid range per filter is 0.5–2.0; our speeds fit in one filter
        if abs(atempo - 1.0) > 1e-6:
            cmd.extend(["-filter:a", f"atempo={atempo:.4f}"])
        cmd.extend(["-codec:a", "libmp3lame", "-q:a", "4", str(mid)])
        subprocess.run(cmd, check=True)
        out_path.write_bytes(mid.read_bytes())


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


def _atempo_for_rate(rate: str) -> float:
    return RATE_TO_ATEMPO.get((rate or "").strip(), 1.0)


async def synthesize_full(
    text: str,
    gender: str,
    rate: str,
    *,
    on_progress: ProgressCb | None = None,
) -> bytes:
    """Synthesize full text via Gemini TTS; return a single MP3 (merged if chunked).

    ``rate`` is an Edge-style string (e.g. ``+25%``); speed is applied with ffmpeg
    atempo after synthesis because Gemini has no Edge-style rate parameter.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY missing")

    voice = voice_for_gender(gender)
    atempo = _atempo_for_rate(rate)
    chunks = split_text(text, TTS_CHUNK_MIN, TTS_CHUNK_MAX)
    if not chunks:
        raise ValueError("empty text")

    timeout = GEMINI_TTS_TIMEOUT_SEC

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        part_paths: list[Path] = []
        for i, chunk in enumerate(chunks):
            if on_progress and i == 0:
                await on_progress("convert")
            part = td_path / f"part_{i:04d}.mp3"

            async def _one(ch=chunk, out=part):
                pcm, sr = await asyncio.wait_for(
                    asyncio.to_thread(_synthesize_pcm_sync, ch, voice),
                    timeout=timeout,
                )
                if not pcm:
                    raise RuntimeError("empty pcm")
                await asyncio.to_thread(_pcm_to_mp3, pcm, sr, out, atempo)

            await _one()
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
