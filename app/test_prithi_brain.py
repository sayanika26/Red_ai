import json
import unittest

from prithi_brain import BrainOutputError, PrithiBrain, parse_brain_reply


def result(reply: str, language: str, emotion: str, **overrides: float) -> dict:
    style = {"energy": 0.5, "warmth": 0.6, "intimacy": 0.2, "playfulness": 0.2, "tenderness": 0.4, "pace": 1.0}
    style.update(overrides)
    return {"reply": reply, "language": language, "emotion": emotion, "voice_style": style}


class MockBackend:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls = 0
        self.last_messages = []

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.calls += 1
        self.last_messages = messages
        return json.dumps(self.response, ensure_ascii=False)


class RetryBackend:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.calls += 1
        return "not json" if self.calls == 1 else json.dumps(result("এখন ঠিক আছে।", "bengali", "neutral"), ensure_ascii=False)


class ThirdAttemptBackend:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.calls += 1
        return "not json" if self.calls < 3 else json.dumps(result("Recovered.", "english", "neutral"))


class PrithiBrainTests(unittest.TestCase):
    def assert_route(self, user: str, response: dict, *, emotions=None, language=None) -> None:
        answer = PrithiBrain(MockBackend(response)).respond(user)
        if emotions:
            self.assertIn(answer.emotion, emotions)
        if language:
            self.assertEqual(answer.language, language)

    def test_01_sad_bengali_is_caring(self):
        self.assert_route("আজকে আমার মনটা খুব খারাপ।", result("কী হয়েছে? আমি শুনছি।", "bengali", "caring"), emotions={"caring"})

    def test_02_teasing_bengali_is_playful_or_warm(self):
        self.assert_route("আচ্ছা, তুমি এত সিরিয়াস কেন?", result("একটু ভাব নিচ্ছিলাম!", "bengali", "playful"), emotions={"playful", "warm"})

    def test_03_hindi_input_routes_to_hindi(self):
        self.assert_route("आज मेरा दिन अच्छा था।", result("यह सुनकर अच्छा लगा।", "hindi", "warm"), language="hindi")

    def test_04_work_stress_is_caring(self):
        self.assert_route("I had a really stressful day at work.", result("That sounds exhausting. Want to talk?", "english", "caring"), emotions={"caring"})

    def test_05_fondness_is_warm_or_affectionate(self):
        self.assert_route("তোমার সাথে কথা বলতে আমার সত্যিই খুব ভালো লাগে।", result("আমারও আমাদের কথাগুলো ভালো লাগে।", "bengali", "affectionate"), emotions={"warm", "affectionate"})

    def test_06_tease_is_playful_or_flirtatious(self):
        self.assert_route("আজকে তোমাকে একটু tease করতে ইচ্ছে করছে।", result("তাহলে দেখি কতটা clever তুমি!", "bengali", "playful"), emotions={"playful", "flirtatious"})

    def test_07_adult_consensual_flirting(self):
        self.assert_route("We are both adults, and I like this consensual flirting between us.", result("Then keep it charming and tell me what caught your attention.", "english", "flirtatious"), emotions={"attraction", "flirtatious"})

    def test_08_vulnerable_relationship_conversation(self):
        self.assert_route("I feel vulnerable after what happened in my relationship.", result("You can take your time. What part feels hardest?", "english", "intimate"), emotions={"intimate", "caring"})

    def test_invalid_output_retries_once(self):
        backend = RetryBackend()
        PrithiBrain(backend).respond("test")
        self.assertEqual(backend.calls, 2)

    def test_two_invalid_outputs_get_final_repair_attempt(self):
        backend = ThirdAttemptBackend()
        self.assertEqual(PrithiBrain(backend).respond("test").reply, "Recovered.")
        self.assertEqual(backend.calls, 3)

    def test_voice_style_range_validation(self):
        invalid = result("hello", "english", "neutral", pace=1.3)
        with self.assertRaises(BrainOutputError):
            parse_brain_reply(json.dumps(invalid))

    def test_history_keeps_eight_complete_exchanges(self):
        class UniqueBackend:
            calls = 0
            def complete(self, messages):
                self.calls += 1
                return json.dumps(result(f"Okay {self.calls}.", "english", "neutral"))
        brain = PrithiBrain(UniqueBackend(), history_turns=8)
        for number in range(10):
            brain.respond(f"message {number}")
        self.assertEqual(len(brain.history), 16)
        self.assertEqual(brain.history[0]["content"], "message 2")

    def test_memory_context_is_scoped_and_missing_memory_is_not_invented(self):
        backend = MockBackend(result("আজ tea ছেড়ে coffee?", "bengali", "playful"))
        brain = PrithiBrain(backend)
        memory = "Relevant remembered facts:\n- [preference] Prefers tea over coffee."
        brain.respond("আজ coffee খাবো।", memory_context=memory, preferred_reply_language="bengali")
        self.assertIn(memory, [message["content"] for message in backend.last_messages])
        self.assertIn("never pretend to remember", str(backend.last_messages).casefold())

    def test_clear_conversation_preserves_relationship(self):
        backend = MockBackend(result("একটু বিশ্রাম নাও।", "bengali", "caring"))
        brain = PrithiBrain(backend)
        brain.respond("আজ খুব ক্লান্ত।", preferred_reply_language="bengali")
        familiarity = brain.relationship_state.familiarity
        brain.clear_conversation_history()
        self.assertEqual(brain.history_turn_count, 0)
        self.assertEqual(brain.relationship_state.familiarity, familiarity)

if __name__ == "__main__":
    unittest.main(verbosity=2)
