import json
import os
import warnings
import wave
from pathlib import Path

from google.cloud import texttospeech


PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_DIR / "voice_auditions" / "emotion_tests"
TEXT = "আজকে তোমার দিনটা কেমন গেল? তুমি চাইলে আমার সাথে একটু কথা বলতে পারো।"

CHIRP_TESTS = (
    ("neutral", "leda_neutral.wav", None),
    ("warm", "leda_warm_attempt.wav", 0.96),
    ("playful", "leda_playful_attempt.wav", 1.06),
    ("caring", "leda_caring_attempt.wav", 0.92),
)
CHIRP_VOICE = "bn-IN-Chirp3-HD-Leda"
CHIRP_LANGUAGE = "bn-IN"

GEMINI_MODEL = "gemini-2.5-flash-tts"
GEMINI_VOICE = "Leda"
GEMINI_LANGUAGE = "bn-IN"
GEMINI_TESTS = (
    (
        "neutral",
        "gemini_neutral.wav",
        "Natural everyday conversation, calm, clear, young adult Indian female delivery.",
    ),
    (
        "warm",
        "gemini_warm.wav",
        "Warm, gentle, emotionally present, slightly slower, comforting but natural.",
    ),
    (
        "playful",
        "gemini_playful.wav",
        "Light, clever, playful, slightly teasing, energetic but not exaggerated.",
    ),
    (
        "caring",
        "gemini_caring.wav",
        "Soft, reassuring, attentive, emotionally supportive, calm and sincere.",
    ),
)


def inspect_wav(path: Path) -> dict[str, object]:
    if path.stat().st_size <= 44:
        raise ValueError("WAV is empty or header-only")
    with wave.open(str(path), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        frames = wav_file.getnframes()
    if sample_rate <= 0 or frames <= 0:
        raise ValueError("WAV contains no playable audio frames")
    return {
        "path": str(path),
        "duration": round(frames / sample_rate, 3),
        "sample_rate": sample_rate,
        "file_size": path.stat().st_size,
    }


def write_new(path: Path, content: bytes) -> None:
    with path.open("xb") as output_file:
        output_file.write(content)


def main() -> None:
    credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials or not Path(credentials).is_file():
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS does not point to an existing file")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_names = [item[1] for item in CHIRP_TESTS] + [item[1] for item in GEMINI_TESTS]
    existing = [str(OUTPUT_DIR / name) for name in all_names if (OUTPUT_DIR / name).exists()]
    if existing:
        raise FileExistsError(f"Refusing to overwrite existing emotion auditions: {existing}")

    client = texttospeech.TextToSpeechClient()
    results: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")

        # Chirp 3 HD has documented pace control, but no emotion/style prompt.
        for style, filename, speaking_rate in CHIRP_TESTS:
            path = OUTPUT_DIR / filename
            audio_kwargs = {"audio_encoding": texttospeech.AudioEncoding.LINEAR16}
            if speaking_rate is not None:
                audio_kwargs["speaking_rate"] = speaking_rate
            print(
                f"CHIRP REQUEST style={style} voice={CHIRP_VOICE} "
                f"speaking_rate={speaking_rate if speaking_rate is not None else 'default'}"
            )
            try:
                response = client.synthesize_speech(
                    input=texttospeech.SynthesisInput(text=TEXT),
                    voice=texttospeech.VoiceSelectionParams(
                        language_code=CHIRP_LANGUAGE,
                        name=CHIRP_VOICE,
                    ),
                    audio_config=texttospeech.AudioConfig(**audio_kwargs),
                )
                write_new(path, response.audio_content)
                result = {
                    "model_voice": CHIRP_VOICE,
                    "style": style,
                    "control": (
                        "default settings"
                        if speaking_rate is None
                        else f"speaking_rate={speaking_rate}"
                    ),
                    **inspect_wav(path),
                }
                results.append(result)
                print("SUCCESS " + json.dumps(result, ensure_ascii=False))
            except Exception as exc:
                if path.exists() and path.stat().st_size <= 44:
                    path.unlink()
                error = {
                    "model_voice": CHIRP_VOICE,
                    "style": style,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                errors.append(error)
                print("FAILED " + json.dumps(error, ensure_ascii=False))

        # The first neutral request doubles as the Gemini-TTS availability check.
        gemini_available = False
        for index, (style, filename, prompt) in enumerate(GEMINI_TESTS):
            if index > 0 and not gemini_available:
                break
            path = OUTPUT_DIR / filename
            print(
                f"GEMINI REQUEST style={style} model={GEMINI_MODEL} "
                f"voice={GEMINI_VOICE} language={GEMINI_LANGUAGE}"
            )
            try:
                response = client.synthesize_speech(
                    input=texttospeech.SynthesisInput(text=TEXT, prompt=prompt),
                    voice=texttospeech.VoiceSelectionParams(
                        language_code=GEMINI_LANGUAGE,
                        name=GEMINI_VOICE,
                        model_name=GEMINI_MODEL,
                    ),
                    audio_config=texttospeech.AudioConfig(
                        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                    ),
                )
                write_new(path, response.audio_content)
                result = {
                    "model_voice": f"{GEMINI_MODEL}/{GEMINI_VOICE}",
                    "style": style,
                    "control": f"SynthesisInput.prompt={prompt}",
                    **inspect_wav(path),
                }
                results.append(result)
                gemini_available = True
                print("SUCCESS " + json.dumps(result, ensure_ascii=False))
            except Exception as exc:
                if path.exists() and path.stat().st_size <= 44:
                    path.unlink()
                error = {
                    "model_voice": f"{GEMINI_MODEL}/{GEMINI_VOICE}",
                    "style": style,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                errors.append(error)
                print("FAILED " + json.dumps(error, ensure_ascii=False))
                if index == 0:
                    print("GEMINI AVAILABILITY unavailable; remaining Gemini styles not attempted")
                    break

        print(
            "SUMMARY "
            + json.dumps(
                {
                    "successful": len(results),
                    "failed_requests": len(errors),
                    "gemini_available": gemini_available,
                }
            )
        )
        if captured:
            for item in captured:
                print(f"WARNING {item.category.__name__}: {item.message}")
        else:
            print("WARNING none")


if __name__ == "__main__":
    main()
