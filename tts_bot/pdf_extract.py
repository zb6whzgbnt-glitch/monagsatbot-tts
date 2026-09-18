from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("tts_bot.pdf")

# Treat as empty if extraction yields no alphanumeric characters
# (covers scanned/image-only PDFs that return whitespace or page-break junk).
_MIN_ALNUM = 1


class PdfExtractError(Exception):
    """PDF could not be opened or parsed."""


def clean_extracted_text(text: str) -> str:
    """Normalize whitespace and drop form-feeds / control junk."""
    if not text:
        return ""
    text = text.replace("\x0c", "\n")
    text = text.replace("\u00a0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0e-\x1f]", "", text)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    lines = [ln.strip() for ln in text.split("\n")]
    out: list[str] = []
    blank = 0
    for ln in lines:
        if not ln:
            blank += 1
            if blank <= 1:
                out.append("")
        else:
            blank = 0
            out.append(ln)
    return "\n".join(out).strip()


def is_meaningful_text(text: str) -> bool:
    return sum(1 for ch in text if ch.isalnum()) >= _MIN_ALNUM


def _pdftotext(path: str) -> str:
    exe = shutil.which("pdftotext")
    if not exe:
        raise FileNotFoundError("pdftotext not found")
    result = subprocess.run(
        [exe, "-nopgbrk", "-enc", "UTF-8", "-q", path, "-"],
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or b"").decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"pdftotext failed: {err or result.returncode}")
    return result.stdout.decode("utf-8", errors="replace")


def _pypdf(path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(path)
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:
            raise RuntimeError("encrypted pdf") from exc
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _pdfminer(path: str) -> str:
    from pdfminer.high_level import extract_text

    return extract_text(path) or ""


def extract_pdf_text(data: bytes) -> str:
    """Extract text from PDF bytes. Prefer poppler pdftotext; then pypdf; then pdfminer.

    Returns cleaned text, or "" if the file opened but had no extractable text.
    Raises PdfExtractError if the file is not a readable PDF.
    """
    if not data:
        raise PdfExtractError("empty file")
    head = data[:1024]
    if b"%PDF" not in head:
        raise PdfExtractError("not a pdf")

    extractors = (
        ("pdftotext", _pdftotext),
        ("pypdf", _pypdf),
        ("pdfminer", _pdfminer),
    )

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        path = tmp.name
        last_err: Exception | None = None
        opened = False
        for name, fn in extractors:
            try:
                raw = fn(path)
            except Exception as exc:
                last_err = exc
                log.info("pdf extractor %s failed: %s", name, str(exc)[:200])
                continue
            opened = True
            cleaned = clean_extracted_text(raw)
            if is_meaningful_text(cleaned):
                log.info("pdf extracted via %s chars=%s", name, len(cleaned))
                return cleaned
            log.info("pdf extractor %s returned no meaningful text", name)
            # pdftotext opened the file; empty output means image-only / no text layer.
            if name == "pdftotext":
                return ""

    if not opened and last_err is not None:
        raise PdfExtractError(str(last_err)[:200]) from last_err
    return ""


def extract_pdf_file(path: str | Path) -> str:
    return extract_pdf_text(Path(path).read_bytes())
