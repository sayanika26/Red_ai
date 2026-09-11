import io
import json
import os
import secrets
import sys
import wave
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from prithi_chat import load_local_env


CASES = (
    ("bengali", "bengali", ROOT / "voice_auditions/google/leda_multilingual/leda_bengali.wav"),
    ("banglish", "bengali", ROOT / "voice_auditions/google/leda_multilingual/leda_banglish.wav"),
    ("hindi", "hindi", ROOT / "voice_auditions/google/leda_multilingual/leda_hindi.wav"),
    ("english", "english", ROOT / "voice_auditions/google/leda_multilingual/leda_english.wav"),
)


def main() -> None:
    load_local_env()
    token = os.environ.get("PRITHI_WEB_ACCESS_TOKEN", "")
    port = int(os.environ.get("PRITHI_WEB_PORT", "8000"))
    if not token:
        raise RuntimeError("PRITHI_WEB_ACCESS_TOKEN is missing")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Prithi-User": secrets.token_urlsafe(32),
    }
    rows = []
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", headers=headers, timeout=300) as client:
        for name, requested_language, audio_path in CASES:
            if not audio_path.is_file():
                raise FileNotFoundError(audio_path)
            with audio_path.open("rb") as audio:
                response = client.post(
                    "/api/voice-turn",
                    files={"audio": (audio_path.name, audio, "audio/wav")},
                    data={"language": requested_language},
                )
            response.raise_for_status()
            body = response.json()
            if body["language"] != requested_language:
                raise AssertionError(f"{name}: expected {requested_language}, got {body['language']}")
            generated = client.get(body["audio_url"])
            generated.raise_for_status()
            with wave.open(io.BytesIO(generated.content), "rb") as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                duration = frames / rate
            if frames <= 0 or rate <= 0:
                raise AssertionError(f"{name}: generated audio is empty")
            transcript = body["transcript"]
            bengali_chars = sum("\u0980" <= char <= "\u09ff" for char in transcript)
            devanagari_chars = sum("\u0900" <= char <= "\u097f" for char in transcript)
            latin_chars = sum(char.isascii() and char.isalpha() for char in transcript)
            row = {
                "case": name,
                "requested_language": requested_language,
                "transcript": transcript,
                "reply": body["reply"],
                "reply_language": body["language"],
                "emotion": body["emotion"],
                "stt_time": body["stt_time"],
                "llm_time": body["llm_time"],
                "tts_time": body["tts_time"],
                "total_time": body["total_time"],
                "audio_duration": duration,
                "audio_bytes": len(generated.content),
                "audio_retrieval": "PASS",
                "bengali_dominant": bengali_chars > devanagari_chars if name in {"bengali", "banglish"} else None,
                "english_words_preserved": latin_chars > 0 if name == "banglish" else None,
            }
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    output = ROOT / "runtime" / "validation" / "prithi_v1_voice_results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    output.chmod(0o600)
    print(f"VOICE_PIPELINE_CASES={len(rows)} PASS")
    print("BROWSER_PLAYBACK=MANUAL_CONFIRMATION_REQUIRED")


if __name__ == "__main__":
    main()
