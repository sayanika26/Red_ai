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
PROJECT_DIR = Path(__file__).resolve().parent.parent
REFERENCE_AUDIO = PROJECT_DIR / "reference" / "prithi_reference_clean.wav"
TESTS = (
    ("আমার নাম পৃথি।", PROJECT_DIR / "output" / "prithi_test_03_name.wav"),
    ("হ্যালো। তুমি কেমন আছো?", PROJECT_DIR / "output" / "prithi_test_03_sentence.wav"),
)


def save_audio(audio: object, destination: Path) -> None:
    array = np.asarray(audio)
    if array.dtype == np.int16:
        array = array.astype(np.float32) / 32768.0
    else:
        array = array.astype(np.float32)
    sf.write(destination, array, 24_000, subtype="PCM_16")


def main() -> None:
    if not REFERENCE_AUDIO.is_file():
        raise FileNotFoundError(f"Clean reference not found: {REFERENCE_AUDIO}")
    for _, output in TESTS:
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite existing output: {output}")

    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none'}")
    print(f"Reference audio: {REFERENCE_AUDIO}")
    print(f"Reference transcript: {REFERENCE_TRANSCRIPT}")

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        print(f"Model loading: {MODEL_ID}")
        model = AutoModel.from_pretrained(MODEL_ID, trust_remote_code=True)
        print("Model loading: complete")

        for index, (text, output) in enumerate(TESTS, start=1):
            print(f"Test {index} text: {text}")
            print(
                "Model call: model(text, ref_audio_path=str(REFERENCE_AUDIO), "
                "ref_text=REFERENCE_TRANSCRIPT)"
            )
            started = time.perf_counter()
            with torch.inference_mode():
                audio = model(
                    text,
                    ref_audio_path=str(REFERENCE_AUDIO),
                    ref_text=REFERENCE_TRANSCRIPT,
                )
            save_audio(audio, output)
            print(f"Test {index} generation time: {time.perf_counter() - started:.2f} seconds")
            print(f"Test {index} output: {output}")

        print("Warnings:")
        if captured:
            for item in captured:
                print(f"- {item.category.__name__}: {item.message}")
        else:
            print("- none")


if __name__ == "__main__":
    main()
