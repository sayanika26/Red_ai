"""Conservative rejection of obvious decoder failures; never rewrites speech."""
import re
import unicodedata
from collections import Counter

RETRY_MESSAGE = "I couldn't understand that clearly. Please try once more."


def assess_transcript(result, language):
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
    return {'passed': not reasons, 'reasons': reasons}
