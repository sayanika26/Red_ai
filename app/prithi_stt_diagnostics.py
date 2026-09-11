"""Explicit, time-limited browser microphone comparisons; never invokes Brain/TTS."""
import json
import math
import os
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

import numpy as np
from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from prithi_stt import BENGALI_PROMPT, transcribe_audio

DIAGNOSTIC_DIR = Path(__file__).resolve().parent.parent / "runtime" / "stt_diagnostics"
REFERENCES = [
    "আজকে তোমার সাথে একটু গল্প করতে চাই।",
    "সারাদিন অনেক কাজ ছিল, এখন একটু ক্লান্ত লাগছে।",
    "তুমি আজকে কী করছিলে? আমার কথা মনে পড়েছিল?",
    "আজকে mood টা একটু off, তাই তোমার সাথে কথা বলতে এলাম।",
    "কালকে সকালে আমার একটু তাড়াতাড়ি উঠতে হবে।",
]


def inspect_audio(source, converted):
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,sample_rate,channels:format=format_name", "-of", "json", str(source)],
        capture_output=True, text=True, check=True, timeout=15,
    )
    info = json.loads(probe.stdout)
    with wave.open(str(converted), "rb") as wav:
        rate, channels, width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
        if (rate, channels, width) != (16000, 1, 2):
            raise ValueError("Expected mono 16 kHz PCM16")
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float64) / 32768
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    rms = float(np.sqrt(np.mean(samples ** 2))) if samples.size else 0.0
    blocks = [float(np.sqrt(np.mean(block ** 2))) for block in np.array_split(samples, max(1, math.ceil(len(samples) / 320))) if len(block)]
    return {
        "source": info, "duration": len(samples) / rate,
        "rms": rms, "rms_dbfs": round(20 * math.log10(max(rms, 1e-12)), 2),
        "peak": peak, "clipping": bool(np.any(np.abs(samples) >= 32767 / 32768)),
        "approx_silence_fraction": sum(v < 0.00316 for v in blocks) / max(1, len(blocks)),
        "level": "Low" if rms < 0.00316 else "High" if peak >= 0.98 else "Good",
        "conversion": "WAV, mono, 16000 Hz, PCM signed 16-bit; no effects",
    }


def compare_sample(path):
    baseline = {"vad_filter": True, "vad_parameters": {"min_silence_duration_ms": 2000, "speech_pad_ms": 300}}
    a = transcribe_audio(path, "bengali", decoding=baseline)
    c = transcribe_audio(path, "bengali", decoding={**baseline, "initial_prompt": BENGALI_PROMPT})
    # Installed faster-whisper defaults beam_size=5; do not fabricate a difference.
    e = transcribe_audio(path, "bengali", decoding={**baseline, "initial_prompt": BENGALI_PROMPT, "beam_size": 1})
    f = transcribe_audio(path, "bengali", decoding={**baseline, "initial_prompt": BENGALI_PROMPT, "beam_size": 5, "vad_filter": False})
    return {
        "A": a, "B": {**a, "equivalent_to": "A: existing browser conversion already standardizes audio and forces bn"},
        "C": c, "D": {**c, "equivalent_to": "C: installed default beam_size is already 5"},
        "E_beam1": e, "F_no_vad": f,
    }


def register_diagnostics(app, require_token, current_session, converter, allowed_types, config):
    enabled = os.environ.get("PRITHI_STT_DIAGNOSTICS", "false").lower() == "true"
    # Each process session expires automatically; app/.env stays false.
    expires = time.monotonic() + 7200
    lock = threading.Lock()
    counts = {}

    def active():
        return enabled and time.monotonic() < expires

    @app.get("/api/stt-diagnostics", dependencies=[Depends(require_token)])
    def status(session_id: str = Depends(current_session)):
        return {"enabled": active(), "saved_samples": counts.get(session_id, 0), "references": REFERENCES,
                "note": "Explicit diagnostic recordings are saved for this test. Brain and TTS are not called."}

    @app.post("/api/stt-diagnostics", dependencies=[Depends(require_token)])
    async def record(audio: UploadFile = File(...), consent: str = Form("false"), reference: str = Form(""), session_id: str = Depends(current_session)):
        if not active():
            raise HTTPException(403, "Diagnostic capture is disabled or expired")
        if consent != "true":
            raise HTTPException(400, "Explicit diagnostic recording consent is required")
        if len(reference) > 2000:
            raise HTTPException(400, "Reference is too long")
        mime = (audio.content_type or "").split(";", 1)[0].lower()
        suffix = allowed_types.get(mime)
        if suffix is None:
            raise HTTPException(415, "Unsupported audio type")
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "A diagnostic comparison is already running")
        try:
            if counts.get(session_id, 0) >= 5:
                raise HTTPException(409, "Five samples captured. Review results before recording more.")
            with tempfile.TemporaryDirectory(prefix="prithi_stt_diag_") as directory:
                source, converted = Path(directory) / ("input" + suffix), Path(directory) / "input.wav"
                size = 0
                with source.open("xb") as target:
                    while chunk := await audio.read(1024 * 1024):
                        size += len(chunk)
                        if size > config.max_upload_bytes:
                            raise HTTPException(413, "Recording upload is too large")
                        target.write(chunk)
                if not size:
                    raise HTTPException(400, "Recording is empty. Please try again.")
                try:
                    conversion_time, duration = await run_in_threadpool(converter, source, converted, config.max_recording_seconds)
                    metrics = await run_in_threadpool(inspect_audio, source, converted)
                except Exception:
                    raise HTTPException(422, "Audio decoding failed. Please try recording again.")
                sample_id = secrets.token_hex(16)
                DIAGNOSTIC_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
                destination = DIAGNOSTIC_DIR / sample_id
                destination.mkdir(mode=0o700)
                shutil.copyfile(source, destination / ("browser" + suffix))
                shutil.copyfile(converted, destination / "input.wav")
                for saved in destination.iterdir():
                    saved.chmod(0o600)
                try:
                    results = await run_in_threadpool(compare_sample, converted)
                except Exception:
                    raise HTTPException(422, "STT comparison failed; diagnostic audio was retained for inspection.")
                number = counts.get(session_id, 0) + 1
                payload = {"sample_id": sample_id, "sample_number": number, "reference": reference,
                           "reference_confirmed": False, "browser_mime": audio.content_type,
                           "forced_language": "bn", "audio": metrics, "conversion_time": conversion_time,
                           "results": results}
                with (destination / "result.json").open("x", encoding="utf-8") as output:
                    json.dump(payload, output, ensure_ascii=False, indent=2)
                (destination / "result.json").chmod(0o600)
                counts[session_id] = number
                return payload
        finally:
            await audio.close()
            lock.release()
