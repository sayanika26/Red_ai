import csv
import os
import time
import wave
from collections import Counter
from pathlib import Path

from google.cloud import texttospeech


PROJECT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = PROJECT_DIR / "dataset" / "metadata" / "recording_script_v1.csv"
OUTPUT_ROOT = PROJECT_DIR / "dataset" / "synthetic_google_leda"
METADATA_CSV = PROJECT_DIR / "dataset" / "metadata" / "google_leda_generation_v1.csv"
REQUIRED_COLUMNS = {"clip_id", "language", "emotion", "text", "audio_filename"}
OUTPUT_COLUMNS = [
    "clip_id",
    "language",
    "emotion",
    "text",
    "audio_filename",
    "voice_id",
    "language_code",
    "output_path",
    "duration",
    "sample_rate",
    "file_size",
    "status",
    "error",
]
VOICE_MAP = {
    "bengali": ("bn-IN-Chirp3-HD-Leda", "bn-IN"),
    "hindi": ("hi-IN-Chirp3-HD-Leda", "hi-IN"),
    "english": ("en-IN-Chirp3-HD-Leda", "en-IN"),
}
VALID_STATUSES = {"SUCCESS", "FAILED", "SKIPPED_EXISTING"}
REQUEST_DELAY_SECONDS = 0.20


def count_chars(text: str, start: int, end: int) -> int:
    return sum(start <= ord(char) <= end for char in text)


def select_voice(language: str, text: str) -> tuple[str, str]:
    if language in VOICE_MAP:
        return VOICE_MAP[language]
    if language != "mixed":
        raise ValueError(f"Unsupported language label: {language}")

    bengali_count = count_chars(text, 0x0980, 0x09FF)
    devanagari_count = count_chars(text, 0x0900, 0x097F)
    if bengali_count > devanagari_count:
        return VOICE_MAP["bengali"]
    if devanagari_count > bengali_count:
        return VOICE_MAP["hindi"]
    raise ValueError(
        "Mixed-language row is ambiguous: Bengali and Devanagari character counts are equal"
    )


def inspect_wav(path: Path) -> tuple[float, int, int]:
    if path.stat().st_size <= 44:
        raise ValueError("WAV is zero-byte or header-only")
    with wave.open(str(path), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
        if sample_rate <= 0 or frame_count <= 0:
            raise ValueError("WAV has no playable audio frames")
        duration = frame_count / sample_rate
    if duration <= 0:
        raise ValueError("WAV duration is not positive")
    return duration, sample_rate, path.stat().st_size


def write_metadata(rows: list[dict[str, object]]) -> None:
    temp_path = METADATA_CSV.with_suffix(".csv.tmp")
    with temp_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp_path, METADATA_CSV)


def result_base(
    row: dict[str, str], voice_id: str, language_code: str, output_path: Path
) -> dict[str, object]:
    return {
        "clip_id": row["clip_id"],
        "language": row["language"],
        "emotion": row["emotion"],
        "text": row["text"],
        "audio_filename": row["audio_filename"],
        "voice_id": voice_id,
        "language_code": language_code,
        "output_path": str(output_path),
        "duration": "",
        "sample_rate": "",
        "file_size": "",
        "status": "",
        "error": "",
    }


def main() -> None:
    credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials or not Path(credentials).is_file():
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS does not point to an existing file")

    with INPUT_CSV.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Input CSV is missing required columns: {sorted(missing)}")
        source_rows = list(reader)
    if len(source_rows) != 40:
        raise ValueError(f"Expected 40 input rows, found {len(source_rows)}")

    filenames = [row["audio_filename"] for row in source_rows]
    if len(set(filenames)) != len(filenames):
        raise ValueError("Input CSV contains duplicate audio filenames")
    for filename in filenames:
        if Path(filename).name != filename or not filename.lower().endswith(".wav"):
            raise ValueError(f"Unsafe or invalid audio filename: {filename}")

    for language in ("bengali", "hindi", "english", "mixed"):
        (OUTPUT_ROOT / language).mkdir(parents=True, exist_ok=True)
    METADATA_CSV.parent.mkdir(parents=True, exist_ok=True)

    client = texttospeech.TextToSpeechClient()
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
    )
    results: list[dict[str, object]] = []

    for index, row in enumerate(source_rows, start=1):
        language = row["language"].strip().lower()
        output_path = OUTPUT_ROOT / language / row["audio_filename"]
        try:
            voice_id, language_code = select_voice(language, row["text"])
        except Exception as exc:
            result = result_base(row, "", "", output_path)
            result.update(status="FAILED", error=f"{type(exc).__name__}: {exc}")
            results.append(result)
            write_metadata(results)
            print(f"[{index}/40] FAILED {row['clip_id']}: {result['error']}")
            continue

        result = result_base(row, voice_id, language_code, output_path)
        if output_path.exists():
            try:
                duration, sample_rate, file_size = inspect_wav(output_path)
                result.update(
                    duration=f"{duration:.3f}",
                    sample_rate=sample_rate,
                    file_size=file_size,
                    status="SKIPPED_EXISTING",
                )
            except Exception as exc:
                result.update(
                    status="FAILED",
                    error=f"Existing file is invalid and was not overwritten: {type(exc).__name__}: {exc}",
                )
            results.append(result)
            write_metadata(results)
            print(f"[{index}/40] {result['status']} {row['clip_id']}")
            continue

        print(f"[{index}/40] REQUEST {row['clip_id']} voice={voice_id} language={language_code}")
        try:
            # Exactly one Google TTS request for this CSV row.
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=row["text"]),
                voice=texttospeech.VoiceSelectionParams(
                    language_code=language_code,
                    name=voice_id,
                ),
                audio_config=audio_config,
            )
            with output_path.open("xb") as output_file:
                output_file.write(response.audio_content)
            duration, sample_rate, file_size = inspect_wav(output_path)
            result.update(
                duration=f"{duration:.3f}",
                sample_rate=sample_rate,
                file_size=file_size,
                status="SUCCESS",
            )
            print(f"[{index}/40] SUCCESS {row['clip_id']} duration={duration:.3f}s")
        except Exception as exc:
            if output_path.exists():
                try:
                    inspect_wav(output_path)
                except Exception:
                    output_path.unlink()
            result.update(status="FAILED", error=f"{type(exc).__name__}: {exc}")
            print(f"[{index}/40] FAILED {row['clip_id']}: {result['error']}")

        results.append(result)
        write_metadata(results)
        if index < len(source_rows):
            time.sleep(REQUEST_DELAY_SECONDS)

    # Final validation of every successful or valid pre-existing file.
    for result in results:
        if result["status"] not in {"SUCCESS", "SKIPPED_EXISTING"}:
            continue
        path = Path(str(result["output_path"]))
        try:
            duration, sample_rate, file_size = inspect_wav(path)
            result.update(
                duration=f"{duration:.3f}",
                sample_rate=sample_rate,
                file_size=file_size,
            )
        except Exception as exc:
            result.update(status="FAILED", error=f"Validation failed: {type(exc).__name__}: {exc}")
    write_metadata(results)

    statuses = Counter(str(result["status"]) for result in results)
    successful_by_language = Counter(
        str(result["language"])
        for result in results
        if result["status"] in {"SUCCESS", "SKIPPED_EXISTING"}
    )
    total_duration = sum(
        float(result["duration"])
        for result in results
        if result["status"] in {"SUCCESS", "SKIPPED_EXISTING"}
    )
    total_size = sum(
        int(result["file_size"])
        for result in results
        if result["status"] in {"SUCCESS", "SKIPPED_EXISTING"}
    )
    failed_ids = [str(result["clip_id"]) for result in results if result["status"] == "FAILED"]

    print("=== FINAL SUMMARY ===")
    print("Total expected: 40")
    print(f"Successful: {statuses['SUCCESS']}")
    print(f"Failed: {statuses['FAILED']}")
    print(f"Skipped: {statuses['SKIPPED_EXISTING']}")
    print(f"Bengali successful: {successful_by_language['bengali']}")
    print(f"Hindi successful: {successful_by_language['hindi']}")
    print(f"English successful: {successful_by_language['english']}")
    print(f"Mixed successful: {successful_by_language['mixed']}")
    print(f"Total generated duration: {total_duration:.3f} seconds")
    print(f"Total generated file size: {total_size} bytes")
    print(f"Failed clip IDs: {','.join(failed_ids) if failed_ids else 'none'}")
    print(f"Metadata CSV: {METADATA_CSV}")


if __name__ == "__main__":
    main()
