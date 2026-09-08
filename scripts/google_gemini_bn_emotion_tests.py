import json
import os
import warnings
import wave
from pathlib import Path

from google.cloud import texttospeech


PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_DIR / "voice_auditions" / "emotion_tests_gemini"
MODEL = "gemini-2.5-flash-tts"
SPEAKER = "Leda"
LANGUAGE_CODE = "bn-BD"
SPOKEN_TEXT = "আজকে তোমার দিনটা কেমন গেল? তুমি চাইলে আমার সাথে একটু কথা বলতে পারো।"
TESTS = (
    (
        "neutral",
        "Speak naturally in Bangla, like a young adult South Asian woman in a relaxed everyday conversation. Calm, clear, conversational, not dramatic.",
        "gemini_leda_bn_neutral.wav",
    ),
    (
        "warm",
        "Speak in a warm, gentle, emotionally present way. Slightly softer and slower than normal, reassuring and natural, without sounding theatrical.",
        "gemini_leda_bn_warm.wav",
    ),
    (
        "playful",
        "Speak with a light, clever, playful and mildly teasing tone. Friendly energy, natural conversational rhythm, not exaggerated.",
        "gemini_leda_bn_playful.wav",
    ),
    (
        "caring",
        "Speak softly and sincerely, as if listening carefully to someone who had a difficult day. Reassuring, attentive and emotionally supportive.",
        "gemini_leda_bn_caring.wav",
    ),
)


def inspect_wav(path: Path) -> dict[str, object]:
    if path.stat().st_size <= 44:
        raise ValueError("WAV is empty or header-only")
    with wave.open(str(path), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        frames = wav_file.getnframes()
    if sample_rate <= 0 or frames <= 0:
        raise ValueError("WAV contains no playable audio")
    return {
        "duration": round(frames / sample_rate, 3),
        "sample_rate": sample_rate,
        "file_size": path.stat().st_size,
    }


def main() -> None:
    credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials or not Path(credentials).is_file():
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS does not point to an existing file")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = [str(OUTPUT_DIR / filename) for _, _, filename in TESTS if (OUTPUT_DIR / filename).exists()]
    if existing:
        raise FileExistsError(f"Refusing to overwrite existing Gemini auditions: {existing}")

    client = texttospeech.TextToSpeechClient()
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
    )
    successes = []
    failures = []

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        for style, prompt, filename in TESTS:
            output_path = OUTPUT_DIR / filename
            print(f"REQUEST style={style} model={MODEL} speaker={SPEAKER} language={LANGUAGE_CODE}")
            try:
                # Exactly one Google Gemini-TTS request for this style.
                response = client.synthesize_speech(
                    input=texttospeech.SynthesisInput(
                        text=SPOKEN_TEXT,
                        prompt=prompt,
                    ),
                    voice=texttospeech.VoiceSelectionParams(
                        language_code=LANGUAGE_CODE,
                        name=SPEAKER,
                        model_name=MODEL,
                    ),
                    audio_config=audio_config,
                )
                with output_path.open("xb") as output_file:
                    output_file.write(response.audio_content)
                result = {
                    "model": MODEL,
                    "speaker": SPEAKER,
                    "language_code": LANGUAGE_CODE,
                    "style": style,
                    **inspect_wav(output_path),
                    "output_path": str(output_path),
                }
                successes.append(result)
                print("SUCCESS " + json.dumps(result, ensure_ascii=False))
            except Exception as exc:
                if output_path.exists() and output_path.stat().st_size <= 44:
                    output_path.unlink()
                failure = {
                    "style": style,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                failures.append(failure)
                print("FAILED " + json.dumps(failure, ensure_ascii=False))

        print("SUMMARY " + json.dumps({"successful": len(successes), "failed": len(failures)}))
        if captured:
            for item in captured:
                print(f"WARNING {item.category.__name__}: {item.message}")
        else:
            print("WARNING none")


if __name__ == "__main__":
    main()
