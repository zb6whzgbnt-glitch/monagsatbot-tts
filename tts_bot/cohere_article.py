from __future__ import annotations

import logging
import re

import cohere

from .config import COHERE_API_KEY, COHERE_MODEL

log = logging.getLogger("tts_bot.cohere_article")

MAX_CHARS = 4500
TARGET_MIN = 4000
TARGET_MAX = 4400
TEMPERATURE = 0.8
# Enough headroom for ~4500 Arabic characters.
MAX_TOKENS = 4096

SYSTEM_PROMPT = """\
أنت كاتب مقالات عربية فصيحة. في كل مرة اكتب مقالة واحدة عميقة ومثيرة للتفكير حول سؤال جديد مختلف تختاره بنفسك.

عقد الكتابة (التزم به حرفياً):
1) قبل الكتابة، استلهم داخلياً من حجج متعارضة لمفكرين عبر العصور، لكن لا تَذكر أبداً أي فيلسوف أو مدرسة، ولا تستخدم كلمتي «فلسفة» أو «فلسفي» إطلاقاً.
2) اعرض الآراء المتعارضة بعبارات أنيقة مثل: «هناك رأي آخر يقول…»، «وقد يقول أحدهم…»، «وربما يتبادر إلى الذهن قول آخر…»، «ومن جهة أخرى، قد يرى أحدهم أن…»، «أجل، قد يبدو الأمر كذلك، لكن…»، «وقد يعترض أحدهم ويقول…»، «لكن يمكن النظر إلى الأمر من زاوية أخرى…»، «وربما كانت الحقيقة أقرب إلى…» — ثم قدّم موقفاً جوهرياً حقيقياً، لا حشواً غامضاً.
3) العنوان: سؤال فضول قصير جداً وبسيط (على نمط: هل نعرف أنفسنا؟).
4) مسار الإجابة: مثال من الحياة اليومية، ثم تعميق تدريجي، آراء مضادة منصفة، بلا إجابة نهائية مبكرة، بلا قوائم نقطية، بلا نصائح تحفيزية أو كليشيهات تطوير الذات.
5) اللغة: عربية فصحى أنيقة وبسيطة. استخدم باعتدال: ربما، أجل، لكن، ومع ذلك، لعل…
6) ليست مقالة نصائح تحفيزية.
7) الطول المفضّل 4000–4400 حرفاً (مع المسافات)، ولا يتجاوز أبداً 4500 حرفاً بما فيها المسافات.
8) الخاتمة: ارجع إلى سؤال الافتتاح، اختم بخاتمة متوازنة قوية دون ادعاء يقين نهائي، ثم اطرح سؤالاً قصيراً مفتوحاً واحداً.
9) صيغة الإخراج فقط: السطر الأول = العنوان وحده، ثم سطر فارغ، ثم نص المقال. بلا عناوين ماركداون. بلا مقدمة مثل «إليك المقال» أو أي تعليق خارج النص.
"""


def _client() -> cohere.ClientV2:
    if not COHERE_API_KEY:
        raise RuntimeError("COHERE_API_KEY missing")
    return cohere.ClientV2(api_key=COHERE_API_KEY)


def _extract_text(response) -> str:
    message = getattr(response, "message", None)
    if message is None:
        return ""
    content = getattr(message, "content", None) or []
    parts: list[str] = []
    for item in content:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    return "".join(parts).strip()


def _chat(messages: list[dict], *, temperature: float = TEMPERATURE) -> str:
    client = _client()
    response = client.chat(
        model=COHERE_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=MAX_TOKENS,
    )
    return _extract_text(response)


def _parse_article(raw: str) -> tuple[str, str, str]:
    text = (raw or "").strip()
    # Strip accidental markdown heading markers on first line.
    text = re.sub(r"^#+\s*", "", text)
    if "\n" in text:
        title, rest = text.split("\n", 1)
        body = rest.lstrip("\n").strip()
    else:
        title, body = text, ""
    title = title.strip().strip("*").strip()
    full = f"{title}\n\n{body}".strip() if body else title
    return title, body, full


def _truncate_at_sentence(text: str, limit: int = MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # Prefer Arabic/Latin sentence enders near the end.
    best = -1
    for sep in ("؟", "!", "！", ".", "。", "…"):
        idx = cut.rfind(sep)
        if idx > best and idx >= int(limit * 0.7):
            best = idx
    if best >= 0:
        return cut[: best + 1].rstrip()
    # Fallback: last whitespace
    idx = cut.rfind(" ")
    if idx >= int(limit * 0.7):
        return cut[:idx].rstrip()
    return cut.rstrip()


def _enforce_limit(title: str, body: str, full: str) -> tuple[str, str, str]:
    if len(full) <= MAX_CHARS:
        return title, body, full
    # Keep title intact; shrink body.
    overhead = len(title) + 2  # title + blank line
    body_limit = max(0, MAX_CHARS - overhead)
    body = _truncate_at_sentence(body, body_limit)
    full = f"{title}\n\n{body}".strip()
    if len(full) > MAX_CHARS:
        full = _truncate_at_sentence(full, MAX_CHARS)
        title, body, full = _parse_article(full)
    return title, body, full


def generate_article(used_titles: list[str] | None = None) -> dict:
    """Generate one deep Arabic essay via Cohere.

    Returns dict: title, body, full_text, char_count.
    Raises on API/generation failure (caller must not mark title used).
    """
    used = [t.strip() for t in (used_titles or []) if t and str(t).strip()]
    used_block = ""
    if used:
        # Cap list size for prompt budget.
        shown = used[:80]
        bullets = "\n".join(f"- {t}" for t in shown)
        used_block = (
            "عناوين سبق استخدامها (ممنوع تكرارها أو الاقتراب الشديد منها؛ اختر سؤالاً جديداً تماماً):\n"
            f"{bullets}\n\n"
        )

    user_msg = (
        f"{used_block}"
        "اكتب الآن مقالة واحدة جديدة وفق عقد الكتابة في تعليمات النظام. "
        f"اجعل الطول بين {TARGET_MIN} و{TARGET_MAX} حرفاً، وبحد أقصى {MAX_CHARS}."
    )

    raw = _chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
    )
    if not raw or len(raw) < 200:
        raise RuntimeError("empty or too-short Cohere article")

    title, body, full = _parse_article(raw)

    if len(full) > MAX_CHARS:
        # Ask once to shorten, then hard-truncate if still over.
        shorten_user = (
            f"المقال التالي أطول من {MAX_CHARS} حرفاً. أعد كتابته بالكامل بنفس "
            f"العقد والعنوان إن أمكن، بطول {TARGET_MIN}–{TARGET_MAX} حرفاً ودون تجاوز "
            f"{MAX_CHARS}. أخرج بنفس الصيغة: سطر عنوان ثم سطر فارغ ثم النص فقط.\n\n"
            f"{full}"
        )
        try:
            raw2 = _chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": shorten_user},
                ],
                temperature=0.5,
            )
            if raw2 and len(raw2) >= 200:
                title, body, full = _parse_article(raw2)
        except Exception:
            log.exception("shorten pass failed; will truncate")

    title, body, full = _enforce_limit(title, body, full)
    if not title or not body:
        raise RuntimeError("article missing title or body")

    return {
        "title": title,
        "body": body,
        "full_text": full,
        "char_count": len(full),
    }
