import json
import os
import warnings
import wave
from pathlib import Path

from google.cloud import texttospeech


TEXT = "হ্যালো, আজকে তোমার দিনটা কেমন গেল? একটু আমার সাথে গল্প করবে?"
LANGUAGE_CODE = "bn-IN"
PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_DIR / "voice_auditions" / "google"
VOICES = (
    ("bn-IN-Chirp3-HD-Aoede", "google_bn_aoede.wav"),
    ("bn-IN-Chirp3-HD-Kore", "google_bn_kore.wav"),
    ("bn-IN-Chirp3-HD-Leda", "google_bn_leda.wav"),
    ("bn-IN-Chirp3-HD-Achernar", "google_bn_achernar.wav"),
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
    existing = [str(OUTPUT_DIR / filename) for _, filename in VOICES if (OUTPUT_DIR / filename).exists()]
    if existing:
        raise FileExistsError(f"Refusing to overwrite existing audition files: {existing}")

    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=TEXT)
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
    )

    successes = []
    failures = []
    with warnings.catch_warnings(record=True) as captured_warnings:
        warnings.simplefilter("always")
        for voice_id, filename in VOICES:
            output_path = OUTPUT_DIR / filename
            print(f"REQUEST voice={voice_id}")
            voice = texttospeech.VoiceSelectionParams(
                language_code=LANGUAGE_CODE,
                name=voice_id,
            )
            try:
                # Exactly one API request for this voice.
                response = client.synthesize_speech(
                    input=synthesis_input,
                    voice=voice,
                    audio_config=audio_config,
                )
                output_path.write_bytes(response.audio_content)
                duration, sample_rate = wav_metadata(output_path)
                result = {
                    "voice_id": voice_id,
                    "output_path": str(output_path),
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
                    "voice_id": voice_id,
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
