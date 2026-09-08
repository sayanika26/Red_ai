import time
import warnings
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from transformers import AutoModel


MODEL_ID = "ai4bharat/IndicF5"
REFERENCE_TRANSCRIPT = (
    "হ্যালো, আমি পৃথি। আজকে তোমার দিনটা কেমন গেল? সারাদিন কী করছিলে? "
    "আমার সাথে একটু গল্প করবে?"
)
GENERATION_TEXT = "হ্যালো, আমি পৃথি। তুমি কেমন আছো?"
PROJECT_DIR = Path(__file__).resolve().parent.parent
REFERENCE_AUDIO = PROJECT_DIR / "reference" / "prithi_reference_clean.wav"
OUTPUT_AUDIO = PROJECT_DIR / "output" / "prithi_test_02.wav"


def main() -> None:
    if not REFERENCE_AUDIO.is_file():
        raise FileNotFoundError(f"Clean reference not found: {REFERENCE_AUDIO}")
    if OUTPUT_AUDIO.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {OUTPUT_AUDIO}")

    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none'}")
    print("Exact model call:")
    print("model(GENERATION_TEXT, ref_audio_path=str(REFERENCE_AUDIO), ref_text=REFERENCE_TRANSCRIPT)")
    print(f"  GENERATION_TEXT={GENERATION_TEXT!r}")
    print(f"  ref_audio_path={str(REFERENCE_AUDIO)!r}")
    print(f"  ref_text={REFERENCE_TRANSCRIPT!r}")

    started = time.perf_counter()
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        print(f"Model loading: {MODEL_ID}")
        model = AutoModel.from_pretrained(MODEL_ID, trust_remote_code=True)
        print("Model loading: complete")
        print("Generation: starting")
        with torch.inference_mode():
            audio = model(
                GENERATION_TEXT,
                ref_audio_path=str(REFERENCE_AUDIO),
                ref_text=REFERENCE_TRANSCRIPT,
            )
        array = np.asarray(audio)
        if array.dtype == np.int16:
            array = array.astype(np.float32) / 32768.0
        else:
            array = array.astype(np.float32)
        sf.write(OUTPUT_AUDIO, array, 24_000, subtype="PCM_16")
        elapsed = time.perf_counter() - started
        print("Generation: complete")
        print(f"Output path: {OUTPUT_AUDIO}")
        print(f"Generation time: {elapsed:.2f} seconds")
        print("Warnings:")
        if captured:
            for item in captured:
                print(f"- {item.category.__name__}: {item.message}")
        else:
            print("- none")


if __name__ == "__main__":
    main()
