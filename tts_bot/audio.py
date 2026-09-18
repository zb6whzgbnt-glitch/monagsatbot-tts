from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def pcm_to_ogg(pcm: bytes, sample_rate: int = 24000) -> bytes:
    """Convert raw s16le mono PCM to OGG/Opus for Telegram voice notes."""
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "a.pcm"
        dst = Path(td) / "a.ogg"
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
            "-c:a",
            "libopus",
            "-b:a",
            "48k",
            str(dst),
        ]
        subprocess.run(cmd, check=True)
        return dst.read_bytes()


def pcm_to_wav(pcm: bytes, sample_rate: int = 24000) -> bytes:
    """Fallback WAV wrapper around s16le mono PCM."""
    import wave

    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "a.wav"
        with wave.open(str(dst), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm)
        return dst.read_bytes()
