import os
import unittest
from unittest.mock import Mock, patch

import prithi_voice


class PaceProfileTests(unittest.TestCase):
    def test_profile_parsing(self):
        self.assertEqual(prithi_voice.parse_pace_profile("slow"), "slow")
        self.assertEqual(prithi_voice.parse_pace_profile(" NATURAL "), "natural")
        self.assertEqual(prithi_voice.parse_pace_profile("brisk"), "brisk")

    def test_invalid_profile_falls_back_to_natural(self):
        self.assertEqual(prithi_voice.parse_pace_profile("turbo"), "natural")
        profile, pace = prithi_voice.effective_pace("warm", "turbo")
        self.assertEqual(profile, "natural")
        self.assertEqual(pace, 1.05)

    def test_natural_emotion_pace_mapping(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PRITHI_VOICE_EMOTION_PACES_JSON", None)
            for emotion, expected in prithi_voice.DEFAULT_EMOTION_PACES.items():
                with self.subTest(emotion=emotion):
                    self.assertEqual(prithi_voice.effective_pace(emotion, "natural")[1], expected)

    def test_brisk_profile_is_capped(self):
        self.assertEqual(prithi_voice.effective_pace("playful", "brisk")[1], 1.12)


class DeliveryTests(unittest.TestCase):
    def test_punctuation_normalization(self):
        self.assertEqual(
            prithi_voice.normalize_tts_text("হ্যাঁ... ঠিক আছে... তুমি বলো..."),
            "হ্যাঁ, ঠিক আছে, তুমি বলো।",
        )
        self.assertEqual(
            prithi_voice.normalize_tts_text("সত্যি!! তুমি আসবে??"),
            "সত্যি! তুমি আসবে?",
        )

    def test_gemini_delivery_prompt(self):
        prompt = prithi_voice.build_gemini_delivery_prompt("bengali", "warm", 1.05)
        self.assertIn("smooth connected speech", prompt)
        self.assertIn("minimal artificial pauses", prompt)
        self.assertIn("Indian Bengali conversational rhythm", prompt)
        self.assertIn("Do not over-enunciate", prompt)
        self.assertIn("lightly brisk", prompt)

    def test_chirp_receives_numeric_speaking_rate(self):
        response = Mock(audio_content=b"RIFF")
        client = Mock()
        client.synthesize_speech.return_value = response
        prithi_voice._synthesize_chirp(client, "hello", "english", 1.05)
        config = client.synthesize_speech.call_args.kwargs["audio_config"]
        self.assertAlmostEqual(config.speaking_rate, 1.05)


if __name__ == "__main__":
    unittest.main()
