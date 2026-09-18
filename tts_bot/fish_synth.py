from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path

from .chunking import split_text
from .config import (
    FISH_API_KEY,
    FISH_TTS_MODEL,
    FISH_TTS_TIMEOUT_SEC,
    FISH_VOICE_FEMALE,
    FISH_VOICE_MALE,
    RATE_TO_ATEMPO,
    TTS_CHUNK_MAX,
    TTS_CHUNK_MIN,
)

log = logging.getLogger("tts_bot.fish")

ProgressCb = Callable[[str], Awaitable[None]]

_FISH_TTS_URL = "https://api.fish.audio/v1/tts"

# Official SDK client, created lazily.
_client = None


def _sdk_client():
    global _client
    if _client is None:
        if not FISH_API_KEY:
            raise RuntimeError("FISH_API_KEY missing")
        from fishaudio import FishAudio

        _client = FishAudio(api_key=FISH_API_KEY, timeout=FISH_TTS_TIMEOUT_SEC)
    return _client


def voice_for_gender(gender: str) -> str | None:
    """Map male/female to a public Arabic-capable Fish reference_id.

    Empty env value means omit reference_id (Fish default / auto voice).
    Voice-cloning upload UI is out of scope for this version.
    """
    g = (gender or "").lower()
    if g in ("female", "f", "امرأة", "woman"):
        return FISH_VOICE_FEMALE or None
    return FISH_VOICE_MALE or None


def _speed_for_rate(rate: str) -> float:
    """Edge-style rate (e.g. +25%) -> Fish prosody speed (0.5–2.0)."""
    speed = RATE_TO_ATEMPO.get((rate or "").strip(), 1.0)
    return max(0.5, min(2.0, float(speed)))


def _raise_fish_http(status: int, message: str) -> None:
    msg = (message or "").strip() or "unknown error"
    if status == 401:
        raise RuntimeError("Fish Audio 401: invalid or missing API key")
    if status == 402:
        raise RuntimeError("Fish Audio 402: payment required / insufficient credits")
    if status == 429:
        raise RuntimeError("Fish Audio 429: rate limited, try again later")
    raise RuntimeError(f"Fish Audio {status}: {msg[:200]}")


def _raise_fish_error(exc: BaseException) -> None:
    status = getattr(exc, "status", None)
    message = getattr(exc, "message", None) or str(exc)
    if status in (401, 402, 429):
        _raise_fish_http(int(status), str(message))
    name = type(exc).__name__
    if name == "AuthenticationError":
        _raise_fish_http(401, str(message))
    if name == "RateLimitError":
        _raise_fish_http(429, str(message))
    if status:
        raise RuntimeError(f"Fish Audio {status}: {str(message)[:200]}") from exc
    raise RuntimeError(f"Fish Audio error: {str(exc)[:200]}") from exc


def _synthesize_httpx(text: str, reference_id: str | None, speed: float) -> bytes:
    import httpx

    headers = {
        "Authorization": f"Bearer {FISH_API_KEY}",
        "Content-Type": "application/json",
        "model": FISH_TTS_MODEL,
    }
    body: dict = {"text": text, "format": "mp3"}
    if reference_id:
        body["reference_id"] = reference_id
    if abs(speed - 1.0) > 1e-6:
        body["prosody"] = {"speed": speed}

    try:
        resp = httpx.post(
            _FISH_TTS_URL,
            headers=headers,
            json=body,
            timeout=FISH_TTS_TIMEOUT_SEC,
        )
    except httpx.TimeoutException as exc:
        raise RuntimeError("Fish Audio request timed out") from exc

    if resp.status_code != 200:
        detail = ""
        try:
            payload = resp.json()
            detail = str(payload.get("message") or payload)
        except Exception:
            detail = (resp.text or "")[:200]
        _raise_fish_http(resp.status_code, detail)

    audio = resp.content
    if not audio:
        raise RuntimeError("empty fish audio")
    return audio


def _synthesize_one_sync(text: str, reference_id: str | None, speed: float) -> bytes:
    body = (text or "").strip()
    if not body:
        raise ValueError("empty text")
    if not FISH_API_KEY:
        raise RuntimeError("FISH_API_KEY missing")

    log.info(
        "tts model=%s voice=%s speed=%s chars=%s",
        FISH_TTS_MODEL,
        reference_id or "auto",
        speed,
        len(body),
    )

    try:
        from fishaudio import FishAudio  # noqa: F401
        from fishaudio.exceptions import APIError, FishAudioError
    except ImportError:
        log.info("fish-audio-sdk missing; using HTTP fallback")
        return _synthesize_httpx(body, reference_id, speed)

    kwargs: dict = {
        "text": body,
        "model": FISH_TTS_MODEL,
        "format": "mp3",
    }
    if reference_id:
        kwargs["reference_id"] = reference_id
    if abs(speed - 1.0) > 1e-6:
        kwargs["speed"] = speed

    try:
        audio = _sdk_client().tts.convert(**kwargs)
    except Exception as exc:
        _raise_fish_error(exc)
        raise  # unreachable, keeps type checkers happy

    if not audio:
        raise RuntimeError("empty fish audio")
    return audio


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
    """Synthesize full text via Fish Audio TTS; return a single MP3.

    Speed is applied with Fish ``prosody.speed`` (0.5–2.0). Long text is
    chunked like the other engines and merged with ffmpeg.
    """
    if not FISH_API_KEY:
        raise RuntimeError("FISH_API_KEY missing")

    voice = voice_for_gender(gender)
    speed = _speed_for_rate(rate)
    chunks = split_text(text, TTS_CHUNK_MIN, TTS_CHUNK_MAX)
    if not chunks:
        raise ValueError("empty text")

    timeout = FISH_TTS_TIMEOUT_SEC

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        part_paths: list[Path] = []
        for i, chunk in enumerate(chunks):
            if on_progress and i == 0:
                await on_progress("convert")
            part = td_path / f"part_{i:04d}.mp3"

            audio = await asyncio.wait_for(
                asyncio.to_thread(_synthesize_one_sync, chunk, voice, speed),
                timeout=timeout,
            )
            if not audio:
                raise RuntimeError(f"empty audio for chunk {i}")
            part.write_bytes(audio)
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
