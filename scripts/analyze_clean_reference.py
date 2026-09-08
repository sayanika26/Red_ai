from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


PROJECT_DIR = Path(__file__).resolve().parent.parent
SOURCE = PROJECT_DIR / "reference" / "prithi_reference.wav"
DESTINATION = PROJECT_DIR / "reference" / "prithi_reference_clean.wav"
TARGET_RATE = 24_000
TARGET_PEAK = 10 ** (-3.0 / 20.0)
SILENCE_DBFS = -40.0
PADDING_SECONDS = 0.15


def rms_dbfs(samples: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))
    return float("-inf") if rms == 0 else 20.0 * np.log10(rms)


def nonsilent_bounds(samples: np.ndarray, sample_rate: int) -> tuple[int, int]:
    frame = max(1, round(sample_rate * 0.02))
    threshold = 10 ** (SILENCE_DBFS / 20.0)
    mono = samples.mean(axis=1) if samples.ndim == 2 else samples
    active = []
    for start in range(0, len(mono), frame):
        chunk = mono[start : start + frame]
        chunk_rms = np.sqrt(np.mean(np.square(chunk.astype(np.float64))))
        if chunk_rms > threshold:
            active.append((start, min(start + frame, len(mono))))
    if not active:
        raise RuntimeError("Reference contains no audio above the -40 dBFS threshold")
    return active[0][0], active[-1][1]


def main() -> None:
    audio, sample_rate = sf.read(SOURCE, always_2d=True, dtype="float32")
    frames, channels = audio.shape
    duration = frames / sample_rate
    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(np.square(audio.astype(np.float64)))))
    clipped = bool(np.any(np.abs(audio) >= 0.999969))
    start, end = nonsilent_bounds(audio, sample_rate)
    leading_silence = start / sample_rate
    trailing_silence = (frames - end) / sample_rate
    edge_silence = leading_silence + trailing_silence
    frame = max(1, round(sample_rate * 0.02))
    threshold = 10 ** (SILENCE_DBFS / 20.0)
    mono = audio.mean(axis=1)
    silent_samples = 0
    for frame_start in range(0, frames, frame):
        chunk = mono[frame_start : frame_start + frame]
        chunk_rms = np.sqrt(np.mean(np.square(chunk.astype(np.float64))))
        if chunk_rms <= threshold:
            silent_samples += len(chunk)
    total_silence = silent_samples / sample_rate

    print("=== ORIGINAL REFERENCE ANALYSIS ===")
    print(f"Path: {SOURCE}")
    print(f"Duration: {duration:.3f} seconds")
    print(f"Sample rate: {sample_rate} Hz")
    print(f"Channels: {channels}")
    print(f"Peak amplitude: {peak:.6f} ({20*np.log10(peak):.2f} dBFS)")
    print(f"RMS amplitude: {rms:.6f} ({rms_dbfs(audio):.2f} dBFS)")
    print(f"Silence threshold: {SILENCE_DBFS:.1f} dBFS (20 ms frames)")
    print(f"Leading silence: {leading_silence:.3f} seconds")
    print(f"Trailing silence: {trailing_silence:.3f} seconds")
    print(f"Edge silence total: {edge_silence:.3f} seconds")
    print(f"Total silence (including internal pauses): {total_silence:.3f} seconds")
    print(f"Silent proportion: {100*total_silence/duration:.1f}%")
    print(f"Clipping present: {clipped}")

    pad = round(PADDING_SECONDS * sample_rate)
    trim_start = max(0, start - pad)
    trim_end = min(frames, end + pad)
    clean = audio[trim_start:trim_end].mean(axis=1)
    if sample_rate != TARGET_RATE:
        from math import gcd

        divisor = gcd(sample_rate, TARGET_RATE)
        clean = resample_poly(clean, TARGET_RATE // divisor, sample_rate // divisor)
    clean_peak = float(np.max(np.abs(clean)))
    if clean_peak > 0:
        clean = clean * (TARGET_PEAK / clean_peak)
    clean = np.clip(clean, -1.0, 1.0).astype(np.float32)
    sf.write(DESTINATION, clean, TARGET_RATE, subtype="PCM_16")

    written, written_rate = sf.read(DESTINATION, dtype="float32")
    written_peak = float(np.max(np.abs(written)))
    written_rms = float(np.sqrt(np.mean(np.square(written.astype(np.float64)))))
    print("\n=== CLEAN REFERENCE ===")
    print(f"Path: {DESTINATION}")
    print(f"Duration: {len(written)/written_rate:.3f} seconds")
    print(f"Sample rate: {written_rate} Hz")
    print("Channels: 1")
    print(f"Peak amplitude: {written_peak:.6f} ({20*np.log10(written_peak):.2f} dBFS)")
    print(f"RMS amplitude: {written_rms:.6f} ({rms_dbfs(written):.2f} dBFS)")
    print(f"Clipping present: {bool(np.any(np.abs(written) >= 0.999969))}")


if __name__ == "__main__":
    main()
