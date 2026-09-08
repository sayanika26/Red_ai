import argparse
import os
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
    "aroused": "Heightened intimate energy and anticipation. Slightly slower and more expressive while remaining natural and controlled.",
    "affectionate": "Tender, warm, gentle and emotionally close.",
    "pleasure": "Relaxed, pleased, positive and naturally expressive.",
    "intimate": "Soft, private, emotionally vulnerable, trusting and sincere.",
    "flirtatious": "Clever, teasing, confident, playful and subtly intimate.",
}


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
        ),
    )
    return response.audio_content, voice, locale


def _synthesize_gemini(
    client: texttospeech.TextToSpeechClient,
    text: str,
    language: str,
    emotion: str,
) -> tuple[bytes, str, str]:
    locale = LANGUAGES[language]["gemini_locale"]
    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(
            text=text,
            prompt=EMOTION_PROMPTS[emotion],
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


def generate_voice(text: str, language: str, emotion: str) -> dict[str, object]:
    language = language.lower().strip()
    emotion = emotion.lower().strip()
    if language not in LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    if emotion not in EMOTION_PROMPTS:
        raise ValueError(f"Unsupported emotion: {emotion}")
    if not text.strip():
        raise ValueError("Text must not be empty")

    credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials or not Path(credentials).is_file():
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS does not point to an existing file")

    client = texttospeech.TextToSpeechClient()
    started = time.perf_counter()
    fallback = False
    api_error = "none"

    if emotion == "neutral":
        engine = "Google Chirp 3 HD"
        audio, model_voice, locale = _synthesize_chirp(client, text, language)
    else:
        engine = "Google Gemini TTS"
        locale = LANGUAGES[language]["gemini_locale"]
        if language == "bengali":
            print("NOTICE: Bengali expressive mode uses the bn-BD Gemini locale for this prototype.")
        try:
            audio, model_voice, locale = _synthesize_gemini(
                client, text, language, emotion
            )
        except Exception as exc:
            fallback = True
            api_error = f"{type(exc).__name__}: {exc}"
            engine = "Google Chirp 3 HD (fallback)"
            audio, model_voice, locale = _synthesize_chirp(client, text, language)

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
