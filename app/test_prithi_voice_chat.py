import json
import os
import unittest
from unittest.mock import Mock, patch

from prithi_brain import BrainReply, PrithiBrain, VoiceStyle
from prithi_voice_chat import PrithiVoicePipeline, resolve_stt_language


STYLE = VoiceStyle(energy=0.4, warmth=0.8, intimacy=0.2, playfulness=0.1, tenderness=0.8, pace=0.95)


def stt_result(text: str = "hello") -> dict:
    return {
        "text": text,
        "detected_language": "en",
        "language_probability": 0.99,
        "duration": 1.0,
        "transcription_time": 0.1,
        "model": "large-v3-turbo",
        "device": "cuda",
        "compute_type": "float16",
        "model_load_time": 1.0,
    }


class FakeBackend:
    def __init__(self):
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        return json.dumps(
            {
                "reply": "I am listening." if self.calls == 1 else f"I am listening {self.calls}.",
                "language": "english",
                "emotion": "caring",
                "voice_style": STYLE.as_dict(),
            }
        )


class PrithiVoiceChatTests(unittest.TestCase):
    def make_pipeline(self, *, stt=None, brain=None, voice=None, reply_mode="normal"):
        brain = brain or PrithiBrain(FakeBackend(), history_turns=8)
        return PrithiVoicePipeline(
            brain,
            stt=stt or Mock(return_value=stt_result()),
            voice=voice or Mock(return_value={"output_path": "/tmp/reply.wav"}),
            reply_mode=reply_mode,
        )

    @patch("prithi_voice_chat.gpu_snapshot", return_value={"available": True})
    def test_empty_stt_stops_pipeline(self, _gpu):
        brain = Mock()
        voice = Mock()
        pipeline = self.make_pipeline(stt=Mock(return_value=stt_result("")), brain=brain, voice=voice)
        result = pipeline.process_audio("input.wav", "auto")
        self.assertEqual(result["status"], "STT_EMPTY")
        brain.respond.assert_not_called()
        voice.assert_not_called()

    @patch("prithi_voice_chat.gpu_snapshot", return_value={"available": True})
    def test_valid_transcript_reaches_brain(self, _gpu):
        brain = Mock()
        brain.respond.return_value = BrainReply("শুনছি।", "bengali", "caring", STYLE)
        brain.last_generation_time = 0.2
        result = self.make_pipeline(brain=brain).process_audio("input.wav", "bengali")
        brain.respond.assert_called_once_with("hello", preferred_reply_language="bengali")
        self.assertEqual(result["status"], "SUCCESS")

    def test_brain_failure_prevents_tts(self):
        brain = Mock()
        brain.respond.side_effect = RuntimeError("bad JSON twice")
        voice = Mock()
        result = self.make_pipeline(brain=brain, voice=voice).process_audio("input.wav", "auto")
        self.assertEqual(result["status"], "BRAIN_FAILED")
        voice.assert_not_called()

    @patch("prithi_voice_chat.gpu_snapshot", return_value={"available": True})
    def test_tts_failure_retains_reply(self, _gpu):
        result = self.make_pipeline(voice=Mock(side_effect=RuntimeError("TTS down"))).process_audio("input.wav", "auto")
        self.assertEqual(result["status"], "TTS_FAILED")
        self.assertEqual(result["brain"]["reply"], "I am listening.")

    def test_bengali_mapping(self):
        self.assertEqual(resolve_stt_language("bengali"), "bengali")

    def test_hindi_mapping(self):
        self.assertEqual(resolve_stt_language("hindi"), "hindi")

    def test_english_mapping(self):
        self.assertEqual(resolve_stt_language("english"), "english")

    def test_default_stt_language_configuration(self):
        with patch.dict(os.environ, {"PRITHI_DEFAULT_STT_LANGUAGE": "bengali"}):
            self.assertEqual(resolve_stt_language(None), "bengali")

    def test_concise_voice_mode_adds_voice_only_hint(self):
        brain = Mock()
        brain.respond.return_value = BrainReply("শুনছি।", "bengali", "caring", STYLE)
        brain.last_generation_time = 0.2
        self.make_pipeline(brain=brain, reply_mode="concise").process_audio("input.wav", "bengali")
        _, kwargs = brain.respond.call_args
        self.assertIn("1–3", kwargs["response_hint"])

    def test_normal_voice_mode_does_not_add_hint(self):
        brain = Mock()
        brain.respond.return_value = BrainReply("Okay.", "english", "neutral", STYLE)
        brain.last_generation_time = 0.2
        self.make_pipeline(brain=brain, reply_mode="normal").process_audio("input.wav", "english")
        brain.respond.assert_called_once_with("hello", preferred_reply_language="english")

    @patch("prithi_voice_chat.gpu_snapshot", return_value={"available": True})
    def test_rolling_conversation_history(self, _gpu):
        pipeline = self.make_pipeline()
        for _ in range(10):
            pipeline.process_audio("input.wav", "auto")
        self.assertEqual(pipeline.brain.history_turn_count, 8)

    @patch("prithi_voice_chat.gpu_snapshot", return_value={"available": True})
    def test_reset_command_behavior(self, _gpu):
        pipeline = self.make_pipeline()
        pipeline.process_audio("input.wav", "auto")
        pipeline.reset()
        self.assertEqual(pipeline.brain.history_turn_count, 0)
        self.assertIsNone(pipeline.last_result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
