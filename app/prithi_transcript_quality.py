"""Fast, conservative transcript checks; never rewrites what the user said."""
import re
import unicodedata
from collections import Counter

RETRY_MESSAGE = "I couldn't understand that clearly. Please try once more."

_TOKEN = re.compile(r"[\w\u0980-\u09ff\u0900-\u097f]+", re.UNICODE)
_BENGALI_CONTINUATIONS = (
    "এটা", "ওটা", "সেটা", "এইটা", "আগের", "তাই", "তারপর", "ওই কথা",
    "বলছিলাম", "করেছিলাম", "হয়েছিল", "হয়েছিল",
)
_COMMON_HALLUCINATIONS = (
    "thanks for watching", "thank you for watching", "subscribe to the channel",
    "amara.org", "subtitles by", "ধন্যবাদ দেখার জন্য", "চ্যানেলটি সাবস্ক্রাইব",
)
_BENGALI_SEMANTIC_CONFUSIONS = (
    "শারা দিন", "অনেক কাছ ছিল", "অনেক কাছ ছিলো", "আজকি শারা",
)


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN.findall(text.casefold()) if len(token) >= 3}


def _acoustic_confidence(result: dict) -> float:
    """Collapse Whisper signals into a cheap 0..1 risk signal.

    Missing metrics are treated as unknown rather than failure so existing STT
    adapters remain compatible.
    """
    signals: list[float] = []
    if "language_probability" in result:
        signals.append(max(0.0, min(1.0, float(result["language_probability"]))))
    segments = result.get("segment_metrics") or []
    if segments:
        logprob = sum(float(item.get("avg_logprob", 0.0)) for item in segments) / len(segments)
        no_speech = sum(float(item.get("no_speech_prob", 0.0)) for item in segments) / len(segments)
        compression = max(float(item.get("compression_ratio", 0.0)) for item in segments)
        signals.extend((max(0.0, min(1.0, (logprob + 1.5) / 1.35)), 1.0 - max(0.0, min(1.0, no_speech))))
        if compression:
            signals.append(0.2 if compression > 2.4 else 1.0)
    return round(sum(signals) / len(signals), 3) if signals else 0.75


def assess_transcript(result, language, previous_text: str | None = None):
    text = str(result.get('text', '')).strip()
    reasons = []
    if not text:
        reasons.append('empty')
    words = text.split()
    if len(words) >= 12 and Counter(words).most_common(1)[0][1] / len(words) > .6:
        reasons.append('excessive_token_repetition')
    for size in range(3, min(12, len(words)//3)+1):
        if any(words[i:i+size] == words[i+size:i+2*size] == words[i+2*size:i+3*size] for i in range(len(words)-3*size+1)):
            reasons.append('repeated_phrase')
            break
    if language == 'bengali':
        letters = [c for c in text if c.isalpha()]
        bengali = sum('\u0980' <= c <= '\u09ff' for c in letters)
        other_indic = sum('\u0900' <= c <= '\u0dff' and not '\u0980' <= c <= '\u09ff' for c in letters)
        if letters and other_indic / len(letters) > .6:
            reasons.append('inconsistent_indic_script')
        accented_latin = sum(ord(c) > 127 and 'LATIN' in unicodedata.name(c, '') for c in letters)
        # Allows ordinary English/Banglish. Flags substantial foreign accented text
        # only when the requested Bengali transcript has no Bengali at all.
        if not bengali and accented_latin >= 3 and accented_latin / max(1,len(letters)) > .08:
            reasons.append('inconsistent_accented_latin')
    segments = result.get('segment_metrics', [])
    if segments and all(s.get('avg_logprob', 0) < -1.2 and s.get('no_speech_prob', 0) > .8 for s in segments):
        reasons.append('low_confidence_no_speech')
    acoustic_confidence = _acoustic_confidence(result)
    lowered = text.casefold()
    if any(marker in lowered for marker in _COMMON_HALLUCINATIONS):
        reasons.append("likely_decoder_hallucination")
    if language == "bengali" and any(marker in lowered for marker in _BENGALI_SEMANTIC_CONFUSIONS):
        reasons.append("known_bengali_semantic_confusion")

    context_overlap: float | None = None
    if language == "bengali" and previous_text and text:
        previous_tokens, current_tokens = _tokens(previous_text), _tokens(text)
        context_overlap = round(
            len(previous_tokens.intersection(current_tokens)) / max(1, min(len(previous_tokens), len(current_tokens))),
            3,
        )
        is_continuation = any(marker in lowered for marker in _BENGALI_CONTINUATIONS)
        # A context jump alone is normal. Reject only when the wording claims to
        # continue the prior turn *and* Whisper's own signals are also weak.
        if is_continuation and not context_overlap and acoustic_confidence < 0.58:
            reasons.append("low_confidence_context_mismatch")

    if language == "bengali" and text and acoustic_confidence < 0.34:
        reasons.append("low_semantic_confidence")
    reasons = list(dict.fromkeys(reasons))
    return {
        'passed': not reasons,
        'reasons': reasons,
        'semantic_confidence': acoustic_confidence,
        'context_overlap': context_overlap,
    }
