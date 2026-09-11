import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
import prithi_stt
from prithi_web import create_app, WebConfig
from prithi_stt_diagnostics import compare_sample


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        config = patch.dict(os.environ, {"PRITHI_STT_BENGALI_PRIMARY": "large-v3-turbo"})
        config.start()
        self.addCleanup(config.stop)

    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            client = TestClient(create_app(config=WebConfig(access_token="test")))
            headers = {"Authorization": "Bearer test"}
            self.assertFalse(client.get("/api/stt-diagnostics", headers=headers).json()["enabled"])
            self.assertEqual(client.post("/api/stt-diagnostics", headers=headers, files={"audio": ("x.wav", b"audio", "audio/wav")}).status_code, 403)

    def test_explicit_consent_required(self):
        with patch.dict(os.environ, {"PRITHI_STT_DIAGNOSTICS": "true"}):
            client = TestClient(create_app(config=WebConfig(access_token="test")))
            self.assertEqual(client.post("/api/stt-diagnostics", headers={"Authorization": "Bearer test"}, files={"audio": ("x.wav", b"audio", "audio/wav")}).status_code, 400)

    def test_prompt_does_not_change_other_languages(self):
        with patch.dict(os.environ, {"PRITHI_STT_BENGALI_PROMPT": "true", "PRITHI_STT_BEAM_SIZE": "1", "PRITHI_STT_BENGALI_VAD": "false"}):
            self.assertIn("initial_prompt", prithi_stt.decoding_options("bengali"))
            for language in ("hindi", "english", "auto"):
                self.assertNotIn("initial_prompt", prithi_stt.decoding_options(language))
                self.assertTrue(prithi_stt.decoding_options(language)["vad_filter"])

    def test_forced_bengali_preserves_banglish(self):
        model = Mock()
        model.transcribe.return_value = (iter([SimpleNamespace(text="আজ mood off")]), SimpleNamespace(language="bn", language_probability=1, duration=2))
        with tempfile.NamedTemporaryFile(suffix=".wav") as f, patch.object(prithi_stt, "_get_model", return_value=(model, "float16", 0)):
            f.write(b"mock"); f.flush()
            result = prithi_stt.transcribe_audio(f.name, "bengali")
        self.assertEqual(model.transcribe.call_args.kwargs["language"], "bn")
        self.assertEqual(result["raw_transcript"], "আজ mood off")
        self.assertEqual(result["normalized_transcript"], result["raw_transcript"])
        self.assertEqual(result["segment_count"], 1)

    def test_comparison_uses_same_audio_and_never_auto(self):
        with patch("prithi_stt_diagnostics.transcribe_audio", return_value={"text": "বাংলা"}) as transcribe:
            results = compare_sample(Path("same.wav"))
        self.assertEqual(transcribe.call_count, 4)
        self.assertEqual(set(results), {"A", "B", "C", "D", "E_beam1", "F_no_vad"})
        for call in transcribe.call_args_list:
            self.assertEqual(call.args, (Path("same.wav"), "bengali"))

    def test_frontend_upload_runs_after_stop_event(self):
        source = (Path(__file__).parent / "web" / "app.js").read_text()
        self.assertIn('recorder.addEventListener("dataavailable"', source)
        self.assertIn('recorder.addEventListener("stop"', source)
        self.assertIn('recorder.addEventListener("start"', source)
        self.assertIn('if (!blob.size)', source)


if __name__ == "__main__":
    unittest.main()
