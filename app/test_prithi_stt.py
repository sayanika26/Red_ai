import tempfile
import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import prithi_stt
from prithi_stt import language_code, transcribe_audio, validate_result


class PrithiSTTTests(unittest.TestCase):
    def setUp(self):
        self.config = patch.dict(os.environ, {"PRITHI_STT_BENGALI_PRIMARY": "large-v3-turbo"})
        self.config.start()
        self.addCleanup(self.config.stop)

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
        self.assertFalse(result["model_reused"])

    def test_singleton_initializes_once_under_concurrency(self):
        created = object()

        def construct(*args, **kwargs):
            del args, kwargs
            time.sleep(0.02)
            return created

        with (
            patch.object(prithi_stt, "_MODEL", None),
            patch.object(prithi_stt, "_COMPUTE_TYPE", None),
            patch.object(prithi_stt, "_MODEL_LOAD_TIME", None),
            patch.object(prithi_stt, "ensure_model_downloaded", return_value=Path("/mock/model")),
            patch.object(prithi_stt, "WhisperModel", side_effect=construct) as constructor,
        ):
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: prithi_stt._get_model(), range(4)))
        self.assertEqual(constructor.call_count, 1)
        self.assertTrue(all(result[0] is created for result in results))
        self.assertEqual(sum(result[2] > 0 for result in results), 1)

    def test_large_bengali_model_reused_across_threads(self):
        created = object()
        with (patch.object(prithi_stt, "_LARGE_MODEL", None),
              patch.object(Path, "is_file", return_value=True),
              patch.object(prithi_stt, "WhisperModel", return_value=created) as constructor):
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: prithi_stt._get_large_model(), range(4)))
        self.assertEqual(constructor.call_count, 1)
        self.assertTrue(all(result[0] is created for result in results))
        self.assertEqual(sum(result[2] == 0 for result in results), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
