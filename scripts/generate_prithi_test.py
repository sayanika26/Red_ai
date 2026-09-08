import sys
import time
import warnings
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from transformers import AutoModel


MODEL_ID = "ai4bharat/IndicF5"
PLACEHOLDER = "REFERENCE_TRANSCRIPT_HERE"

# ---------------------------------------------------------------------------
# REQUIRED EDIT BEFORE RUNNING:
# Replace REFERENCE_TRANSCRIPT_HERE below with the exact, word-for-word
# transcript spoken in reference/prithi_reference.wav.
# Keep the transcript in the same language/script as the recording.
# ---------------------------------------------------------------------------
REFERENCE_TRANSCRIPT = (
    "হ্যালো, আমি পৃথি। আজকে তোমার দিনটা কেমন গেল? সারাদিন কী করছিলে? "
    "আমার সাথে একটু গল্প করবে?"
)

TEXT_TO_GENERATE = (
    "হ্যালো, আমি পৃথি। আজকে তোমার সাথে কথা বলতে পেরে আমার খুব ভালো লাগছে। "
    "বলো, তোমার দিনটা কেমন গেল?"
)

PROJECT_DIR = Path(__file__).resolve().parent.parent
REFERENCE_AUDIO = PROJECT_DIR / "reference" / "prithi_reference.wav"
OUTPUT_AUDIO = PROJECT_DIR / "output" / "prithi_test_01.wav"


def main() -> None:
    print(f"Python: {sys.version.split()[0]}")
    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    else:
        print("GPU: none (CPU fallback)")

    if not REFERENCE_AUDIO.is_file():
        raise FileNotFoundError(f"Reference audio not found: {REFERENCE_AUDIO}")

    # Safety guard: no model download/loading or generation occurs until edited.
    if REFERENCE_TRANSCRIPT.strip() == PLACEHOLDER:
        print("WARNING: Generation stopped before model loading.")
        print(
            "Edit REFERENCE_TRANSCRIPT in this file and replace "
            f"{PLACEHOLDER} with the exact transcript of {REFERENCE_AUDIO}."
        )
        return

    OUTPUT_AUDIO.parent.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    started_at = time.perf_counter()

    with warnings.catch_warnings(record=True) as captured_warnings:
        warnings.simplefilter("always")

        print(f"Model loading: starting {MODEL_ID} on {device}")
        model = AutoModel.from_pretrained(MODEL_ID, trust_remote_code=True)
        try:
            model = model.to(device)
        except (AttributeError, NotImplementedError) as exc:
            warnings.warn(
                f"Model wrapper could not be moved with .to({device}): {exc}. "
                "IndicF5 will use its own device selection.",
                RuntimeWarning,
            )
        if hasattr(model, "eval"):
            model.eval()
        print("Model loading: complete")

        print("Generation: starting")
        with torch.inference_mode():
            audio = model(
                TEXT_TO_GENERATE,
                ref_audio_path=str(REFERENCE_AUDIO),
                ref_text=REFERENCE_TRANSCRIPT,
            )

        audio_array = np.asarray(audio)
        if audio_array.dtype == np.int16:
            audio_array = audio_array.astype(np.float32) / 32768.0
        else:
            audio_array = audio_array.astype(np.float32)

        sf.write(OUTPUT_AUDIO, audio_array, samplerate=24000)
        print("Generation: complete")
        print(f"Output path: {OUTPUT_AUDIO}")
        print(f"Generation time: {time.perf_counter() - started_at:.2f} seconds")

        if captured_warnings:
            print("Warnings:")
            for item in captured_warnings:
                print(f"- {item.category.__name__}: {item.message}")
        else:
            print("Warnings: none")


if __name__ == "__main__":
    main()
