import json
import os
import warnings
import wave
from pathlib import Path

from google.cloud import texttospeech


PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_DIR / "voice_auditions" / "google" / "leda_multilingual"
TESTS = (
    {
        "label": "Bengali",
        "voice_id": "bn-IN-Chirp3-HD-Leda",
        "language_code": "bn-IN",
        "text": "হ্যালো, আজকে তোমার দিনটা কেমন গেল? একটু আমার সাথে গল্প করবে?",
        "filename": "leda_bengali.wav",
    },
    {
        "label": "Hindi",
        "voice_id": "hi-IN-Chirp3-HD-Leda",
        "language_code": "hi-IN",
        "text": "आज तुम्हारा दिन कैसा रहा? थोड़ा मेरे साथ बात करोगे?",
        "filename": "leda_hindi.wav",
    },
    {
        "label": "Indian English",
        "voice_id": "en-IN-Chirp3-HD-Leda",
        "language_code": "en-IN",
        "text": "Hey, tell me how your day went. I would really like to hear about it.",
        "filename": "leda_english.wav",
    },
    {
        "label": "Bengali-English mixed",
        "voice_id": "bn-IN-Chirp3-HD-Leda",
        "language_code": "bn-IN",
        "text": "আজকে work কেমন ছিল? খুব busy ছিলে নাকি? Tell me what happened.",
        "filename": "leda_banglish.wav",
    },
)


def wav_metadata(path: Path) -> tuple[float, int]:
    with wave.open(str(path), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        duration = wav_file.getnframes() / sample_rate
    return duration, sample_rate


def main() -> None:
    credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials or not Path(credentials).is_file():
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS does not point to an existing file")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = [str(OUTPUT_DIR / test["filename"]) for test in TESTS if (OUTPUT_DIR / test["filename"]).exists()]
    if existing:
        raise FileExistsError(f"Refusing to overwrite existing multilingual auditions: {existing}")

    client = texttospeech.TextToSpeechClient()
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
    )
    successes = []
    failures = []

    with warnings.catch_warnings(record=True) as captured_warnings:
        warnings.simplefilter("always")
        for test in TESTS:
            output_path = OUTPUT_DIR / test["filename"]
            print(
                f"REQUEST label={test['label']} voice={test['voice_id']} "
                f"language={test['language_code']}"
            )
            try:
                # Exactly one API request for this test.
                response = client.synthesize_speech(
                    input=texttospeech.SynthesisInput(text=test["text"]),
                    voice=texttospeech.VoiceSelectionParams(
                        language_code=test["language_code"],
                        name=test["voice_id"],
                    ),
                    audio_config=audio_config,
                )
                output_path.write_bytes(response.audio_content)
                duration, sample_rate = wav_metadata(output_path)
                result = {
                    "label": test["label"],
                    "voice_id": test["voice_id"],
                    "language_code": test["language_code"],
                    "path": str(output_path),
                    "file_size": output_path.stat().st_size,
                    "duration": round(duration, 3),
                    "sample_rate": sample_rate,
                }
                successes.append(result)
                print("SUCCESS " + json.dumps(result, ensure_ascii=False))
            except Exception as exc:
                if output_path.exists():
                    output_path.unlink()
                result = {
                    "label": test["label"],
                    "voice_id": test["voice_id"],
                    "language_code": test["language_code"],
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                failures.append(result)
                print("FAILED " + json.dumps(result, ensure_ascii=False))

        print("SUMMARY " + json.dumps({"successful": len(successes), "failed": len(failures)}))
        if captured_warnings:
            for item in captured_warnings:
                print(f"WARNING {item.category.__name__}: {item.message}")
        else:
            print("WARNING none")


if __name__ == "__main__":
    main()
