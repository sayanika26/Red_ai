import argparse
import ctypes
import gc
import os
import threading
import time
from pathlib import Path
from typing import Any

import nvidia.cublas


def _load_private_cuda12_runtime() -> None:
    library_dir = Path(next(iter(nvidia.cublas.__path__))) / "lib"
    for name in ("libcublasLt.so.12", "libcublas.so.12"):
        path = library_dir / name
        if path.is_file():
            ctypes.CDLL(str(path), mode=ctypes.RTLD_GLOBAL)


_load_private_cuda12_runtime()

from faster_whisper import WhisperModel
from faster_whisper.utils import download_model


MODEL_NAME = "large-v3-turbo"
PROJECT_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = PROJECT_DIR / "runtime" / "whisper" / "models" / MODEL_NAME
SUPPORTED_LANGUAGES = {"auto": None, "bengali": "bn", "hindi": "hi", "english": "en"}
SUPPORTED_FORMATS = {".wav", ".mp3", ".m4a", ".flac"}
BENGALI_PROMPT = "এটি স্বাভাবিক ভারতীয় বাংলা কথোপকথন। কথার মধ্যে মাঝে মাঝে English words থাকতে পারে। বাংলা শব্দ বাংলা লিপিতে লিখুন এবং পরিচিত English words English-এ রাখতে পারেন।"


def decoding_options(language: str) -> dict[str, Any]:
    options = {"vad_filter": True, "vad_parameters": {"min_silence_duration_ms": 2000, "speech_pad_ms": 300}}
    if language_code(language) == "bn":
        if os.environ.get("PRITHI_STT_BENGALI_PROMPT", "false").lower() == "true":
            options["initial_prompt"] = BENGALI_PROMPT
        beam = int(os.environ.get("PRITHI_STT_BEAM_SIZE", "5"))
        if beam not in (1, 2, 3, 4, 5):
            raise ValueError("PRITHI_STT_BEAM_SIZE must be between 1 and 5")
        options["beam_size"] = beam
        options["vad_filter"] = os.environ.get("PRITHI_STT_BENGALI_VAD", "true").lower() == "true"
    return options

_MODEL: WhisperModel | None = None
_COMPUTE_TYPE: str | None = None
_MODEL_LOAD_TIME: float | None = None
_MODEL_LOCK = threading.Lock()
_TRANSCRIBE_SEMAPHORE = threading.BoundedSemaphore(2)
_LARGE_MODEL = None
_LARGE_LOCK = threading.Lock()


def _get_large_model():
    global _LARGE_MODEL
    with _LARGE_LOCK:
        if _LARGE_MODEL is not None:
            return _LARGE_MODEL, "float16", 0.0
        path = MODEL_PATH.parent / "large-v3"
        if not (path / "model.bin").is_file():
            raise RuntimeError("Configured Bengali large-v3 model is missing")
        started = time.perf_counter()
        _LARGE_MODEL = WhisperModel(str(path), device="cuda", compute_type="float16")
        return _LARGE_MODEL, "float16", time.perf_counter() - started


def language_code(language: str) -> str | None:
    normalized = language.lower().strip()
    if normalized not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language '{language}'. Choose: {', '.join(SUPPORTED_LANGUAGES)}")
    return SUPPORTED_LANGUAGES[normalized]


def ensure_model_downloaded() -> Path:
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not (MODEL_PATH / "model.bin").is_file():
        download_model(MODEL_NAME, output_dir=str(MODEL_PATH))
    return MODEL_PATH


def _get_model() -> tuple[WhisperModel, str, float]:
    global _MODEL, _COMPUTE_TYPE, _MODEL_LOAD_TIME
    if _MODEL is not None:
        return _MODEL, _COMPUTE_TYPE or "unknown", 0.0
    with _MODEL_LOCK:
        if _MODEL is not None:
            return _MODEL, _COMPUTE_TYPE or "unknown", 0.0
        model_path = ensure_model_downloaded()
        failures = []
        for compute_type in ("float16", "int8_float16"):
            started = time.perf_counter()
            try:
                model = WhisperModel(str(model_path), device="cuda", compute_type=compute_type)
                _MODEL = model
                _COMPUTE_TYPE = compute_type
                _MODEL_LOAD_TIME = time.perf_counter() - started
                return model, compute_type, _MODEL_LOAD_TIME
            except Exception as exc:
                failures.append(f"{compute_type}: {type(exc).__name__}: {exc}")
        raise RuntimeError("GPU Whisper initialization failed; CPU fallback was not used. " + " | ".join(failures))


def unload_model() -> bool:
    """Release the process-level Whisper reference; the next request reloads it."""
    global _MODEL, _COMPUTE_TYPE, _MODEL_LOAD_TIME
    with _MODEL_LOCK:
        if _MODEL is None:
            return False
        _MODEL = None
        _COMPUTE_TYPE = None
        _MODEL_LOAD_TIME = None
    gc.collect()
    return True


def validate_result(result: dict[str, Any]) -> None:
    required = {"text", "detected_language", "language_probability", "duration", "transcription_time", "model", "device", "compute_type", "model_load_time", "model_reused"}
    missing = required - set(result)
    if missing:
        raise ValueError(f"STT result missing fields: {sorted(missing)}")
    if not isinstance(result["text"], str):
        raise ValueError("STT text must be a string")
    if not isinstance(result["detected_language"], str) or not result["detected_language"]:
        raise ValueError("Detected language must be non-empty")
    if not 0.0 <= float(result["language_probability"]) <= 1.0:
        raise ValueError("Language probability must be between 0 and 1")
    if float(result["duration"]) < 0 or float(result["transcription_time"]) < 0:
        raise ValueError("Durations must not be negative")
    if result["device"] != "cuda":
        raise ValueError("STT device must be cuda")


def transcribe_audio(audio_path: str | Path, language: str = "auto", *, decoding: dict[str, Any] | None = None) -> dict[str, Any]:
    path = Path(audio_path).expanduser().resolve()
    requested_language = language_code(language)
    if not path.is_file():
        raise FileNotFoundError(f"Audio file does not exist: {path}")
    if path.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported audio format: {path.suffix or '(none)'}")
    if path.stat().st_size == 0:
        raise ValueError(f"Audio file is empty: {path}")

    selected_model = os.environ.get("PRITHI_STT_BENGALI_PRIMARY", MODEL_NAME) if requested_language == "bn" else MODEL_NAME
    if selected_model not in (MODEL_NAME, "large-v3"):
        raise ValueError("Unsupported Bengali STT model")
    model, compute_type, load_time = _get_large_model() if selected_model == "large-v3" else _get_model()
    options = decoding_options(language) if decoding is None else dict(decoding)
    if set(options) - {"vad_filter", "vad_parameters", "beam_size", "initial_prompt", "temperature", "best_of", "condition_on_previous_text"}:
        raise ValueError("Unsupported decoding override")
    started = time.perf_counter()
    try:
        with _TRANSCRIBE_SEMAPHORE:
            segments, info = model.transcribe(
                str(path),
                language=requested_language,
                task="transcribe",
                **options,
            )
            segments = list(segments)
            text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
    except Exception as exc:
        raise RuntimeError(f"Could not decode/transcribe audio '{path}': {type(exc).__name__}: {exc}") from exc
    result = {
        "text": text,
        "raw_transcript": text,
        "normalized_transcript": text,
        "segment_count": len(segments),
        "segment_metrics": [{"avg_logprob": getattr(s, "avg_logprob", 0), "no_speech_prob": getattr(s, "no_speech_prob", 0), "compression_ratio": getattr(s, "compression_ratio", 0)} for s in segments],
        "forced_language": requested_language,
        "detected_language": info.language,
        "language_probability": float(info.language_probability),
        "duration": float(info.duration),
        "transcription_time": time.perf_counter() - started,
        "model": selected_model,
        "device": "cuda",
        "compute_type": compute_type,
        "model_load_time": load_time,
        "model_reused": load_time == 0.0,
    }
    validate_result(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Transcribe audio locally with Prithi STT")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--language", default="auto", choices=sorted(SUPPORTED_LANGUAGES))
    args = parser.parse_args()
    result = transcribe_audio(args.audio, args.language)
    print(f"Transcript: {result['text']}")
    print(f"Detected language: {result['detected_language']}")
    print(f"Language probability: {result['language_probability']:.4f}")
    print(f"Audio duration: {result['duration']:.3f} seconds")
    print(f"Transcription time: {result['transcription_time']:.3f} seconds")
    print(f"Model load time: {result['model_load_time']:.3f} seconds")
    print(f"Model: {result['model']}")
    print(f"Device: {result['device']}")
    print(f"Compute type: {result['compute_type']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
