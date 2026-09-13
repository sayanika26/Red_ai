import tempfile
import unittest
from pathlib import Path

from prithi_context import analyze_context
from prithi_learning import LearningStore, learning_signal, prompt_for_behaviors
from prithi_mood import MoodState, MoodStore, blend_voice_style, update_mood
from prithi_roleplay import RoleplayState
from prithi_strategy import compose_adaptive_prompt, select_strategy


class AdaptiveBrainTests(unittest.TestCase):
    def test_context_bengali_support(self):
        state = analyze_context("আজ মনটা খুব খারাপ, একা লাগছে।", "bengali")
        self.assertEqual((state.language, state.user_need), ("bengali", "reassurance"))

    def test_context_banglish_continuity(self):
        self.assertEqual(analyze_context("আজ mood off", "bengali").language, "bengali")

    def test_context_boundary(self):
        self.assertEqual(analyze_context("Stop, normal কথা বলি।", "bengali").boundary_signal, "stop")

    def test_strategy_reassurance(self):
        self.assertEqual(select_strategy(analyze_context("I feel lonely")), "reassurance")

    def test_strategy_deescalation(self):
        self.assertEqual(select_strategy(analyze_context("Stop, not now"), adult_mode=True), "deescalation")

    def test_normal_mode_does_not_select_sensual(self):
        value = select_strategy(analyze_context("Let's talk in an intimate romantic mood"), adult_mode=False)
        self.assertEqual(value, "romantic_reciprocation")

    def test_adult_mode_can_select_sensual(self):
        value = select_strategy(analyze_context("Let's talk in an intimate romantic mood"), adult_mode=True)
        self.assertEqual(value, "sensual_reciprocation")

    def test_mood_changes_are_gradual(self):
        before = MoodState()
        after = update_mood(before, analyze_context("I feel lonely"), "reassurance")
        self.assertLessEqual(max(abs(after.as_dict()[k] - before.as_dict()[k]) for k in before.as_dict()), .12)

    def test_deescalation_reduces_tension(self):
        before = MoodState(romantic_tension=.5, sensual_tension=.5)
        after = update_mood(before, analyze_context("Stop, normal কথা বলি।"), "deescalation", adult_mode=True)
        self.assertLess(after.sensual_tension, before.sensual_tension)

    def test_mood_persistence_and_user_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MoodStore(Path(directory) / "state.db")
            store.save("a", MoodState(warmth=.9))
            self.assertGreater(store.load("a").warmth, store.load("b").warmth)

    def test_voice_style_blending_is_bounded(self):
        result = blend_voice_style({"energy": 1, "warmth": 1, "intimacy": 1, "playfulness": 1, "tenderness": 1, "pace": 1.1}, MoodState())
        self.assertTrue(all(0 <= result[key] <= 1 for key in ("energy", "warmth", "intimacy", "playfulness", "tenderness")))

    def test_roleplay_adult_gate(self):
        with self.assertRaises(PermissionError):
            RoleplayState().start("adult romantic scene", adult_scene=True)

    def test_roleplay_pause_resume_reset(self):
        state = RoleplayState(); state.start("rainy cafe"); state.pause(); self.assertTrue(state.paused)
        state.resume(); self.assertFalse(state.paused); state.reset(); self.assertFalse(state.active)

    def test_roleplay_stop_deescalates(self):
        state = RoleplayState(); state.start("cafe"); state.apply_boundary("stop"); self.assertFalse(state.active)

    def test_roleplay_prompt_marks_fictional_memory(self):
        state = RoleplayState(); state.start("cafe")
        self.assertIn("do not store as real memory", state.prompt())

    def test_learning_create_and_reinforce(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LearningStore(Path(directory) / "state.db")
            store.learn("u", type="humor", tags=["play"], strategy="teasing_answer", example_style="light tease")
            first = store.relevant("u", ["play"])[0]
            store.learn("u", type="humor", tags=["play"], strategy="teasing_answer", example_style="light tease")
            self.assertGreater(store.relevant("u", ["play"])[0].confidence, first.confidence)

    def test_negative_feedback_weakens_behavior(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LearningStore(Path(directory) / "state.db")
            for _ in range(2): store.learn("u", type="tone", tags=["play"], strategy="teasing_answer", example_style="brief")
            before = store.relevant("u", ["play"])[0].confidence
            store.learn("u", type="tone", tags=["play"], strategy="teasing_answer", example_style="brief", positive=False)
            self.assertLess(store.relevant("u", ["play"])[0].confidence, before)

    def test_learning_user_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LearningStore(Path(directory) / "state.db")
            store.learn("u1", type="tone", tags=["warm"], strategy="warm_validation", example_style="brief")
            self.assertEqual(store.relevant("u2", ["warm"]), [])

    def test_sensitive_learning_excluded(self):
        context = analyze_context("My password is secret")
        self.assertIsNone(learning_signal("My password is secret, nice", context, "direct_answer"))

    def test_prompt_compact_and_composed(self):
        context = analyze_context("আজ মন খারাপ", "bengali")
        prompt = compose_adaptive_prompt(context=context, strategy="reassurance", mood=MoodState().as_dict(), relationship={"trust": .2}, roleplay_prompt="Roleplay inactive.", learned_prompt=prompt_for_behaviors([]), adult_mode=False)
        self.assertIn('"strategy":"reassurance"', prompt)
        self.assertNotIn("chain-of-thought", prompt.casefold())


if __name__ == "__main__":
    unittest.main()
