import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from prithi_mic import (
    EmptyRecordingError,
    MicrophoneError,
    MicrophoneUnavailableError,
    PushToTalkRecorder,
    RecordingConfig,
    cleanup_recording,
    list_input_devices,
    validate_input_device,
)


class FakeStream:
    def __init__(self, callback, samples):
        self.callback = callback
        self.samples = samples
        self.closed = False

    def start(self):
        if self.samples is not None:
            self.callback(self.samples, len(self.samples), None, None)

    def stop(self):
        pass

    def abort(self):
        pass

    def close(self):
        self.closed = True


class FakeBackend:
    def __init__(self, samples=None, devices=None):
        self.samples = samples
        self.devices = devices if devices is not None else [
            {"name": "Mock Mic", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 16000}
        ]

    def query_devices(self, device=None, kind=None):
        if device is None:
            return self.devices
        if device == 99:
            raise RuntimeError("device missing")
        selected = self.devices[int(device)]
        if kind == "input" and selected["max_input_channels"] < 1:
            raise RuntimeError("not input")
        return selected

    def InputStream(self, **kwargs):
        return FakeStream(kwargs["callback"], self.samples)


class PrithiMicTests(unittest.TestCase):
    def test_recording_config_validation(self):
        with self.assertRaises(ValueError):
            RecordingConfig(sample_rate=44100)
        with self.assertRaises(ValueError):
            RecordingConfig(channels=2)

    def test_invalid_input_device(self):
        with self.assertRaisesRegex(ValueError, "Invalid input device"):
            validate_input_device(99, FakeBackend())

    def test_temporary_wav_creation(self):
        samples = np.ones((1600, 1), dtype=np.float32) * 0.1
        recorder = PushToTalkRecorder(RecordingConfig(), FakeBackend(samples))
        with tempfile.TemporaryDirectory() as directory:
            recorder.start()
            path = recorder.stop(directory)
            data, rate = sf.read(path)
            self.assertTrue(path.is_file())
            self.assertEqual(rate, 16000)
            self.assertEqual(data.shape[0], 1600)

    def test_cleanup_behavior(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            path = Path(handle.name)
        self.assertTrue(cleanup_recording(path))
        self.assertFalse(path.exists())
        self.assertFalse(cleanup_recording(path))

    def test_empty_recording_handling(self):
        recorder = PushToTalkRecorder(RecordingConfig(), FakeBackend(samples=None))
        recorder.start()
        with self.assertRaises(EmptyRecordingError):
            recorder.stop()

    def test_microphone_unavailable_error(self):
        backend = FakeBackend(devices=[])
        self.assertEqual(list_input_devices(backend), [])
        with self.assertRaisesRegex(MicrophoneUnavailableError, "Local browser microphone required"):
            validate_input_device(None, backend)

    def test_push_to_talk_state_handling(self):
        samples = np.ones((100, 1), dtype=np.float32)
        recorder = PushToTalkRecorder(RecordingConfig(), FakeBackend(samples))
        self.assertEqual(recorder.state, "idle")
        recorder.start()
        self.assertEqual(recorder.state, "recording")
        with self.assertRaises(MicrophoneError):
            recorder.start()
        path = recorder.stop()
        try:
            self.assertEqual(recorder.state, "idle")
        finally:
            cleanup_recording(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
