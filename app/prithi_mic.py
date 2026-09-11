import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


class MicrophoneError(RuntimeError):
    pass


class MicrophoneUnavailableError(MicrophoneError):
    pass


class EmptyRecordingError(MicrophoneError):
    pass


class PlaybackUnavailableError(MicrophoneError):
    pass


def _sounddevice() -> Any:
    try:
        import sounddevice as sd
    except (ImportError, OSError) as exc:
        raise MicrophoneUnavailableError(
            f"Python audio backend is unavailable: {type(exc).__name__}: {exc}"
        ) from exc
    return sd


@dataclass(frozen=True)
class RecordingConfig:
    sample_rate: int = 16000
    channels: int = 1
    device: int | str | None = None

    def __post_init__(self) -> None:
        if self.sample_rate not in {16000, 24000}:
            raise ValueError("sample_rate must be 16000 or 24000 Hz")
        if self.channels != 1:
            raise ValueError("Prithi microphone recording must be mono")


def list_input_devices(backend: Any | None = None) -> list[dict[str, Any]]:
    sd = backend or _sounddevice()
    try:
        devices = sd.query_devices()
    except Exception as exc:
        raise MicrophoneUnavailableError(
            f"Could not query audio devices: {type(exc).__name__}: {exc}"
        ) from exc
    return [
        {
            "index": index,
            "name": str(device.get("name", "unknown")),
            "max_input_channels": int(device.get("max_input_channels", 0)),
            "default_sample_rate": float(device.get("default_samplerate", 0.0)),
        }
        for index, device in enumerate(devices)
        if int(device.get("max_input_channels", 0)) > 0
    ]


def validate_input_device(device: int | str | None, backend: Any | None = None) -> None:
    sd = backend or _sounddevice()
    available = list_input_devices(sd)
    if not available:
        raise MicrophoneUnavailableError(
            "No microphone input device is visible to this process. Local browser microphone required."
        )
    if device is None:
        return
    try:
        selected = sd.query_devices(device, "input")
    except Exception as exc:
        raise ValueError(f"Invalid input device {device!r}: {exc}") from exc
    if int(selected.get("max_input_channels", 0)) < 1:
        raise ValueError(f"Device {device!r} has no input channels")


class PushToTalkRecorder:
    def __init__(self, config: RecordingConfig, backend: Any | None = None) -> None:
        self.config = config
        self.backend = backend or _sounddevice()
        self.state = "idle"
        self._stream: Any | None = None
        self._blocks: list[np.ndarray] = []
        self.warnings: list[str] = []
        self.last_duration = 0.0

    def _callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        del frames, time_info
        if status:
            self.warnings.append(str(status))
        self._blocks.append(indata.copy())

    def start(self) -> None:
        if self.state != "idle":
            raise MicrophoneError(f"Cannot start recording while state is {self.state}")
        validate_input_device(self.config.device, self.backend)
        self._blocks.clear()
        self.warnings.clear()
        try:
            self._stream = self.backend.InputStream(
                samplerate=self.config.sample_rate,
                channels=1,
                dtype="float32",
                device=self.config.device,
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:
            self._stream = None
            raise MicrophoneUnavailableError(
                f"Could not start microphone recording: {type(exc).__name__}: {exc}"
            ) from exc
        self.state = "recording"

    def stop(self, directory: str | Path | None = None) -> Path:
        if self.state != "recording" or self._stream is None:
            raise MicrophoneError("Recording is not active")
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
            self.state = "idle"
        if not self._blocks:
            raise EmptyRecordingError("Microphone recording contained no audio frames")
        audio = np.concatenate(self._blocks, axis=0)
        self._blocks.clear()
        if audio.size == 0 or audio.shape[0] == 0:
            raise EmptyRecordingError("Microphone recording was empty")
        output_dir = Path(directory).expanduser().resolve() if directory else None
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            prefix="prithi_mic_", suffix=".wav", dir=output_dir, delete=False
        )
        path = Path(handle.name)
        handle.close()
        try:
            sf.write(str(path), audio, self.config.sample_rate, subtype="PCM_16", format="WAV")
        except Exception:
            path.unlink(missing_ok=True)
            raise
        self.last_duration = audio.shape[0] / self.config.sample_rate
        return path

    def cancel(self) -> None:
        if self._stream is not None:
            try:
                self._stream.abort()
                self._stream.close()
            finally:
                self._stream = None
        self._blocks.clear()
        self.state = "idle"


def cleanup_recording(path: str | Path | None) -> bool:
    if path is None:
        return False
    target = Path(path)
    if not target.exists():
        return False
    target.unlink()
    return True


def play_audio(path: str | Path, backend: Any | None = None) -> None:
    sd = backend or _sounddevice()
    try:
        outputs = [d for d in sd.query_devices() if int(d.get("max_output_channels", 0)) > 0]
    except Exception as exc:
        raise PlaybackUnavailableError(f"Could not query playback devices: {exc}") from exc
    if not outputs:
        raise PlaybackUnavailableError("No audio output device is visible to this process")
    audio, sample_rate = sf.read(str(Path(path).expanduser()), dtype="float32")
    try:
        sd.play(audio, sample_rate)
        sd.wait()
    except Exception as exc:
        raise PlaybackUnavailableError(f"Audio playback failed: {type(exc).__name__}: {exc}") from exc
