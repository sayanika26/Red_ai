from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TurnContext:
    user_intent: str
    user_emotion: str
    user_need: str
    subtext: str
    relationship_signal: str
    intimacy_signal: str
    boundary_signal: str
    language: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


_BN = re.compile(r"[\u0980-\u09ff]")
_HI = re.compile(r"[\u0900-\u097f]")


def analyze_context(text: str, selected_language: str | None = None) -> TurnContext:
    value = re.sub(r"\s+", " ", text).strip()
    low = value.casefold()
    if selected_language in {"bengali", "hindi", "english"}:
        language = selected_language
    elif _BN.search(value):
        language = "bengali"
    elif _HI.search(value):
        language = "hindi"
    else:
        language = "english"

    stop = any(x in low for x in ("stop", "not now", "normal কথা", "থাম", "বন্ধ কর", "बस करो", "नहीं अभी"))
    negative = any(x in low for x in ("don't", "do not", "না চাই", "করো না", "পছন্দ না", "मत करो", "नहीं चाहिए"))
    sad = any(x in low for x in ("sad", "lonely", "stress", "upset", "একা", "মন খারাপ", "ক্লান্ত", "চাপ", "उदास", "अकेला", "तनाव"))
    playful = any(x in low for x in ("joke", "tease", "হাসাও", "মজা", "ঠাট্টা", "मज़ाक", "चिढ़ाओ"))
    affection = any(x in low for x in ("miss", "ভালো লাগে", "পছন্দ করি", "কাছে থাকবে", "प्यार", "याद", "अच्छा लगता"))
    intimate = any(x in low for x in ("intimate", "sensual", "romantic", "flirt", "ঘনিষ্ঠ", "রোমান্টিক", "अंतरंग", "रोमांटिक"))
    question = "?" in value or "？" in value or any(x in low for x in ("কি", "কী", "কেন", "क्या", "क्यों", "how", "why", "what"))

    boundary = "stop" if stop else "limit" if negative else "none"
    emotion = "sad" if sad else "playful" if playful else "affectionate" if affection else "neutral"
    need = "reassurance" if sad else "boundary_respect" if boundary != "none" else "connection" if affection or intimate else "answer" if question else "companionship"
    intent = "deescalate" if stop else "set_boundary" if negative else "seek_support" if sad else "play" if playful else "connect" if affection or intimate else "ask" if question else "share"
    relationship = "positive" if affection else "vulnerable" if sad else "neutral"
    intimacy = "explicit_invitation" if intimate else "affectionate" if affection else "none"
    subtext = "needs emotional presence" if sad else "invites reciprocal warmth" if affection else "invites lightness" if playful else "literal"
    return TurnContext(intent, emotion, need, subtext, relationship, intimacy, boundary, language)
