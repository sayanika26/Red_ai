import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from prithi_stt import language_code, transcribe_audio, validate_result


class PrithiSTTTests(unittest.TestCase):
    def test_invalid_path(self):
        with self.assertRaises(FileNotFoundError):
            transcribe_audio("/definitely/missing.wav")

    def test_unsupported_language(self):
        with self.assertRaises(ValueError):
            language_code("french")

    def test_empty_audio(self):
        with tempfile.NamedTemporaryFile(suffix=".wav") as audio:
            with self.assertRaisesRegex(ValueError, "empty"):
                transcribe_audio(audio.name)

    def test_language_mapping(self):
        self.assertIsNone(language_code("auto"))
        self.assertEqual(language_code("bengali"), "bn")
        self.assertEqual(language_code("hindi"), "hi")
        self.assertEqual(language_code("english"), "en")

    @patch("prithi_stt._get_model")
    def test_corrupt_audio_is_reported_cleanly(self, get_model):
        model = Mock()
        model.transcribe.side_effect = RuntimeError("invalid data")
        get_model.return_value = (model, "float16", 1.0)
        with tempfile.NamedTemporaryFile(suffix=".wav") as audio:
            audio.write(b"not a wav")
            audio.flush()
            with self.assertRaisesRegex(RuntimeError, "Could not decode"):
                transcribe_audio(audio.name)

    @patch("prithi_stt._get_model")
    def test_structured_result(self, get_model):
        model = Mock()
        model.transcribe.return_value = (
            iter([SimpleNamespace(text=" hello "), SimpleNamespace(text="world")]),
            SimpleNamespace(language="en", language_probability=0.98, duration=1.5),
        )
        get_model.return_value = (model, "float16", 2.0)
        with tempfile.NamedTemporaryFile(suffix=".wav") as audio:
            audio.write(b"mock audio")
            audio.flush()
            result = transcribe_audio(audio.name, "english")
        validate_result(result)
        self.assertEqual(result["text"], "hello world")
        self.assertEqual(result["device"], "cuda")
        self.assertEqual(result["compute_type"], "float16")


if __name__ == "__main__":
    unittest.main(verbosity=2)
