from __future__ import annotations

# Gemini TTS prebuilt voices: (name, style_ar, gender) gender: F|M
VOICES: list[tuple[str, str, str]] = [
    ("Achernar", "ناعم لطيف", "F"),
    ("Achird", "ودود", "M"),
    ("Algenib", "خشن", "M"),
    ("Algieba", "ناعم", "F"),
    ("Alnilam", "حازم", "M"),
    ("Aoede", "منعش", "F"),
    ("Autonoe", "مشرق", "F"),
    ("Callirrhoe", "مريح", "F"),
    ("Charon", "معلوماتي", "M"),
    ("Despina", "ناعم", "F"),
    ("Enceladus", "مهموس", "M"),
    ("Erinome", "واضح", "F"),
    ("Fenrir", "متحمس", "M"),
    ("Gacrux", "ناضج", "F"),
    ("Iapetus", "واضح", "M"),
    ("Kore", "حازم", "F"),
    ("Laomedeia", "مرح", "F"),
    ("Leda", "شبابي", "F"),
    ("Orus", "حازم", "M"),
    ("Puck", "مرح", "M"),
    ("Pulcherrima", "مباشر", "F"),
    ("Rasalgethi", "معلوماتي", "M"),
    ("Sadachbia", "حيوي", "M"),
    ("Sadaltager", "عالِم", "M"),
    ("Schedar", "متزن", "M"),
    ("Sulafat", "دافئ", "F"),
    ("Umbriel", "مريح", "M"),
    ("Vindemiatrix", "لطيف", "F"),
    ("Zephyr", "مشرق", "F"),
    ("Zubenelgenubi", "عفوي", "M"),
]

VOICE_MAP = {n: (s, g) for n, s, g in VOICES}

TONES = ["محايد", "دافئ", "حماسي", "هادئ", "رسمي", "درامي", "همس"]
SPEEDS = ["بطيء جداً", "بطيء", "عادي", "سريع", "سريع جداً"]
STYLES = ["راوي", "معلّق", "بودكاست", "إعلان", "قصة أطفال", "أخبار"]
DIALECTS = ["فصحى واضحة", "خليجي خفيف", "مصري خفيف", "إنجليزي", "تلقائي"]
FORMALITIES = ["عادي", "رسمي", "ودّي"]


def voice_label(name: str) -> str:
    style, gender = VOICE_MAP.get(name, ("", "?"))
    mark = "♀" if gender == "F" else "♂" if gender == "M" else "·"
    if style:
        return f"{mark} {name} · {style}"
    return f"{mark} {name}"
