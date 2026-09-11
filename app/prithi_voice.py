import argparse
import json
import os
import re
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import texttospeech


APP_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = APP_DIR / "output"
GEMINI_MODEL = "gemini-2.5-flash-tts"
GEMINI_SPEAKER = "Leda"

LANGUAGES = {
    "bengali": {
        "chirp_voice": "bn-IN-Chirp3-HD-Leda",
        "chirp_locale": "bn-IN",
        "gemini_locale": "bn-BD",
    },
    "hindi": {
        "chirp_voice": "hi-IN-Chirp3-HD-Leda",
        "chirp_locale": "hi-IN",
        "gemini_locale": "hi-IN",
    },
    "english": {
        "chirp_voice": "en-IN-Chirp3-HD-Leda",
        "chirp_locale": "en-IN",
        "gemini_locale": "en-IN",
    },
}

EMOTION_PROMPTS = {
    "neutral": "Natural everyday conversation. Calm, clear, conversational, not dramatic.",
    "warm": "Warm, gentle, relaxed and welcoming.",
    "caring": "Soft, reassuring, attentive and sincere.",
    "playful": "Light, clever, playful and mildly teasing.",
    "attraction": "Warm, confident and intimate with subtle romantic attraction. Controlled and natural.",
    "aroused": "Heightened intimate energy and anticipation. Expressive while remaining natural and controlled.",
    "affectionate": "Tender, warm, gentle and emotionally close.",
    "pleasure": "Relaxed, pleased, positive and naturally expressive.",
    "intimate": "Soft, private, emotionally vulnerable, trusting and sincere.",
    "flirtatious": "Clever, teasing, confident, playful and subtly intimate.",
}

DEFAULT_EMOTION_PACES = {
    "neutral": 1.05,
    "warm": 1.05,
    "caring": 1.03,
    "playful": 1.10,
    "flirtatious": 1.08,
    "attraction": 1.06,
    "affectionate": 1.03,
    "intimate": 1.00,
    "pleasure": 1.05,
    "aroused": 1.07,
}
PACE_PROFILE_ADJUSTMENTS = {"slow": -0.05, "natural": 0.0, "brisk": 0.04}
MIN_PACE = 0.90
MAX_PACE = 1.12


def parse_pace_profile(value: str | None) -> str:
    normalized = (value or "natural").strip().lower()
    return normalized if normalized in PACE_PROFILE_ADJUSTMENTS else "natural"


def _configured_emotion_paces() -> dict[str, float]:
    configured = dict(DEFAULT_EMOTION_PACES)
    raw = os.environ.get("PRITHI_VOICE_EMOTION_PACES_JSON", "").strip()
    if not raw:
        return configured
    try:
        overrides = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("PRITHI_VOICE_EMOTION_PACES_JSON must be valid JSON") from exc
    if not isinstance(overrides, dict):
        raise ValueError("PRITHI_VOICE_EMOTION_PACES_JSON must be a JSON object")
    for emotion, pace in overrides.items():
        if emotion not in configured or isinstance(pace, bool) or not isinstance(pace, (int, float)):
            raise ValueError(f"Invalid emotion pace override: {emotion}")
        if not MIN_PACE <= float(pace) <= MAX_PACE:
            raise ValueError(f"Emotion pace for {emotion} must be between {MIN_PACE} and {MAX_PACE}")
        configured[emotion] = float(pace)
    return configured


def effective_pace(
    emotion: str,
    profile: str | None = None,
    voice_style: dict[str, object] | None = None,
) -> tuple[str, float]:
    selected_profile = parse_pace_profile(
        profile if profile is not None else os.environ.get("PRITHI_VOICE_PACE_PROFILE", "natural")
    )
    base = _configured_emotion_paces()[emotion]
    style_adjustment = 0.0
    if voice_style and isinstance(voice_style.get("pace"), (int, float)) and not isinstance(voice_style.get("pace"), bool):
        style_pace = max(0.85, min(1.15, float(voice_style["pace"])))
        style_adjustment = (style_pace - 1.0) * 0.20
    pace = base + PACE_PROFILE_ADJUSTMENTS[selected_profile] + style_adjustment
    return selected_profile, max(MIN_PACE, min(MAX_PACE, round(pace, 3)))


def normalize_tts_text(text: str) -> str:
    normalized = re.sub(r"\s*(?:\.{2,}|…+)\s*", ", ", text.strip())
    normalized = re.sub(r"!{2,}", "!", normalized)
    normalized = re.sub(r"\?{2,}", "?", normalized)
    normalized = re.sub(r",{2,}", ",", normalized)
    normalized = re.sub(r"\s+([,!?।.])", r"\1", normalized)
    normalized = re.sub(r"([,!?।.])(?=[^\s,!?।.])", r"\1 ", normalized)
    normalized = re.sub(r"\s{2,}", " ", normalized).strip()
    if normalized.endswith(","):
        normalized = normalized[:-1] + ("।" if re.search(r"[\u0980-\u09FF]", normalized) else ".")
    return normalized


def _pace_wording(pace: float) -> str:
    if pace <= 1.01:
        return "Use a relaxed but connected natural conversational pace."
    if pace <= 1.055:
        return "Use a lightly brisk everyday conversational pace."
    if pace <= 1.085:
        return "Use a slightly brisk, fluid conversational pace."
    return "Use a lively brisk conversational pace without rushing or losing clarity."


def build_gemini_delivery_prompt(language: str, emotion: str, pace: float) -> str:
    language_direction = {
        "bengali": "Use casual Indian Bengali conversational rhythm while retaining the supported Bengali locale.",
        "hindi": "Use casual spoken Indian Hindi rhythm.",
        "english": "Use casual spoken Indian English rhythm.",
    }[language]
    return " ".join(
        (
            EMOTION_PROMPTS[emotion],
            _pace_wording(pace),
            "Use smooth connected speech with minimal artificial pauses. Do not over-enunciate every word or sound like an announcement.",
            language_direction,
            "Keep the delivery natural, clear and human-like; do not use extreme speed.",
        )
    )


def _inspect_wav(path: Path) -> tuple[float, int]:
    if path.stat().st_size <= 44:
        raise ValueError("Generated WAV is empty or header-only")
    with wave.open(str(path), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        frames = wav_file.getnframes()
    if sample_rate <= 0 or frames <= 0:
        raise ValueError("Generated WAV has no playable audio")
    return frames / sample_rate, sample_rate


def _new_output_path(language: str, emotion: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
    candidate = OUTPUT_DIR / f"prithi_{timestamp}_{language}_{emotion}.wav"
    suffix = 1
    while candidate.exists():
        candidate = OUTPUT_DIR / f"prithi_{timestamp}_{language}_{emotion}_{suffix}.wav"
        suffix += 1
    return candidate


def _synthesize_chirp(
    client: texttospeech.TextToSpeechClient,
    text: str,
    language: str,
    speaking_rate: float,
) -> tuple[bytes, str, str]:
    config = LANGUAGES[language]
    voice = config["chirp_voice"]
    locale = config["chirp_locale"]
    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(
            language_code=locale,
            name=voice,
        ),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            speaking_rate=speaking_rate,
        ),
    )
    return response.audio_content, voice, locale


def _synthesize_gemini(
    client: texttospeech.TextToSpeechClient,
    text: str,
    language: str,
    emotion: str,
    speaking_rate: float,
) -> tuple[bytes, str, str]:
    locale = LANGUAGES[language]["gemini_locale"]
    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(
            text=text,
            prompt=build_gemini_delivery_prompt(language, emotion, speaking_rate),
        ),
        voice=texttospeech.VoiceSelectionParams(
            language_code=locale,
            name=GEMINI_SPEAKER,
            model_name=GEMINI_MODEL,
        ),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        ),
    )
    return response.audio_content, f"{GEMINI_MODEL}/{GEMINI_SPEAKER}", locale


def generate_voice(
    text: str,
    language: str,
    emotion: str,
    voice_style: dict[str, object] | None = None,
    pace_profile: str | None = None,
) -> dict[str, object]:
    language = language.lower().strip()
    emotion = emotion.lower().strip()
    if language not in LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    if emotion not in EMOTION_PROMPTS:
        raise ValueError(f"Unsupported emotion: {emotion}")
    if not text.strip():
        raise ValueError("Text must not be empty")
    selected_profile, speaking_rate = effective_pace(emotion, pace_profile, voice_style)
    delivery_text = normalize_tts_text(text)

    credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials or not Path(credentials).is_file():
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS does not point to an existing file")

    client = texttospeech.TextToSpeechClient()
    started = time.perf_counter()
    fallback = False
    api_error = "none"

    if emotion == "neutral":
        engine = "Google Chirp 3 HD"
        audio, model_voice, locale = _synthesize_chirp(client, delivery_text, language, speaking_rate)
    else:
        engine = "Google Gemini TTS"
        locale = LANGUAGES[language]["gemini_locale"]
        if language == "bengali":
            print("NOTICE: Bengali expressive mode uses the bn-BD Gemini locale for this prototype.")
        try:
            audio, model_voice, locale = _synthesize_gemini(
                client, delivery_text, language, emotion, speaking_rate
            )
        except Exception as exc:
            fallback = True
            api_error = f"{type(exc).__name__}: {exc}"
            engine = "Google Chirp 3 HD (fallback)"
            audio, model_voice, locale = _synthesize_chirp(client, delivery_text, language, speaking_rate)

    output_path = _new_output_path(language, emotion)
    with output_path.open("xb") as output_file:
        output_file.write(audio)
    duration, sample_rate = _inspect_wav(output_path)
    elapsed = time.perf_counter() - started

    result: dict[str, object] = {
        "requested_text": text,
        "language": language,
        "emotion": emotion,
        "tts_engine": engine,
        "model_voice": model_voice,
        "locale": locale,
        "output_path": str(output_path),
        "duration": duration,
        "sample_rate": sample_rate,
        "generation_time": elapsed,
        "fallback_occurred": fallback,
        "api_error": api_error,
        "pace_profile": selected_profile,
        "effective_pace": speaking_rate,
    }
    print(f"Requested text: {text}")
    print(f"Language: {language}")
    print(f"Emotion: {emotion}")
    print(f"TTS engine used: {engine}")
    print(f"Model/voice: {model_voice}")
    print(f"Locale: {locale}")
    print(f"Output path: {output_path}")
    print(f"Duration: {duration:.3f} seconds")
    print(f"Sample rate: {sample_rate} Hz")
    print(f"Generation time: {elapsed:.3f} seconds")
    print(f"Fallback occurred: {fallback}")
    print(f"Pace profile: {selected_profile}")
    print(f"Effective pace: {speaking_rate:.3f}")
    if api_error != "none":
        print(f"Gemini API error: {api_error}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a Prithi voice WAV response")
    parser.add_argument("--text", required=True)
    parser.add_argument("--language", required=True, choices=sorted(LANGUAGES))
    parser.add_argument("--emotion", required=True, choices=sorted(EMOTION_PROMPTS))
    args = parser.parse_args()
    generate_voice(args.text, args.language, args.emotion)


if __name__ == "__main__":
    main()
