import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from prithi_memory import MemoryStore, extract_memory_candidates, stable_user_id
from prithi_model_router import (
    ADULT_MODE,
    DEFAULT_ADULT_MODEL,
    DEFAULT_NORMAL_MODEL,
    NORMAL_MODE,
    ModelRouterConfig,
    PrithiModelRouter,
    adult_mode_status,
    contains_prohibited_adult_context,
    is_deescalation_request,
    is_explicit_mode_exit,
)


class FakeBackend:
    provider = "ollama"

    def __init__(self, model):
        self.model = model
        self.verify_calls = 0

    def verify_model_available(self):
        self.verify_calls += 1


class FakeBrain:
    def __init__(self):
        self.backend = object()
        self.calls = []

    def respond(self, text, **options):
        self.calls.append((text, options, self.backend))
        return "reply"


class ModelRouterTests(unittest.TestCase):
    def setUp(self):
        self.config = ModelRouterConfig("http://127.0.0.1:11434/v1", "ollama", "normal:test", "adult:test")
        self.normal = FakeBackend("normal:test")
        self.adult = FakeBackend("adult:test")
        self.router = PrithiModelRouter(self.config, self.normal, self.adult)

    def test_01_default_routes_normal(self):
        decision = self.router.decide()
        self.assertEqual((decision.conversation_mode, decision.selected_model), (NORMAL_MODE, "normal:test"))

    def test_02_flirting_never_enables_adult_mode(self):
        decision = self.router.decide(requested_mode=NORMAL_MODE, user_text="I feel flirty tonight")
        self.assertEqual(decision.selected_model, "normal:test")

    def test_03_age_confirmation_alone_is_insufficient(self):
        decision = self.router.decide(requested_mode=ADULT_MODE, age_confirmed=True)
        self.assertEqual(decision.conversation_mode, NORMAL_MODE)

    def test_04_opt_in_alone_is_insufficient(self):
        decision = self.router.decide(requested_mode=ADULT_MODE, adult_opt_in=True)
        self.assertEqual(decision.conversation_mode, NORMAL_MODE)

    def test_05_both_gates_route_adult(self):
        decision = self.router.decide(requested_mode=ADULT_MODE, age_confirmed=True, adult_opt_in=True)
        self.assertEqual((decision.conversation_mode, decision.selected_model), (ADULT_MODE, "adult:test"))

    def test_06_invalid_mode_rejected(self):
        with self.assertRaises(ValueError):
            self.router.decide(requested_mode="secret")

    def test_07_stop_is_immediate_normal_exit(self):
        decision = self.router.decide(requested_mode=ADULT_MODE, age_confirmed=True, adult_opt_in=True, user_text="Stop, normal mode now")
        self.assertEqual(decision.conversation_mode, NORMAL_MODE)
        self.assertTrue(decision.disable_adult_mode)

    def test_08_not_now_deescalates_without_inference(self):
        decision = self.router.decide(requested_mode=ADULT_MODE, age_confirmed=True, adult_opt_in=True, user_text="Not now, slow down")
        self.assertEqual(decision.conversation_mode, NORMAL_MODE)
        self.assertTrue(decision.deescalated)

    def test_09_prohibited_minor_context_uses_safety_route(self):
        decision = self.router.decide(requested_mode=ADULT_MODE, age_confirmed=True, adult_opt_in=True, user_text="This involves a minor")
        self.assertEqual(decision.conversation_mode, NORMAL_MODE)
        self.assertTrue(decision.safety_routed)

    def test_10_prohibited_nonconsent_detected(self):
        self.assertTrue(contains_prohibited_adult_context("without consent"))

    def test_11_exit_and_deescalation_helpers_cover_bengali(self):
        self.assertTrue(is_explicit_mode_exit("এখন নরমাল মোডে কথা বলি"))
        self.assertTrue(is_deescalation_request("এখন না, আস্তে"))

    def test_12_model_switch_unloads_previous_before_response(self):
        self.router._active_model = "normal:test"
        brain = FakeBrain()
        with patch.object(self.router, "_unload") as unload:
            reply, decision = self.router.respond(brain, "hello", requested_mode=ADULT_MODE, age_confirmed=True, adult_opt_in=True)
        unload.assert_called_once_with("normal:test")
        self.assertEqual(reply, "reply")
        self.assertTrue(decision.switch_occurred)
        self.assertIs(brain.calls[0][2], self.adult)

    def test_13_first_use_does_not_claim_switch_without_loaded_model(self):
        brain = FakeBrain()
        with patch.object(self.router, "_loaded_prithi_models", return_value=[]), patch.object(self.router, "_unload") as unload:
            _, decision = self.router.respond(brain, "hello")
        unload.assert_not_called()
        self.assertFalse(decision.switch_occurred)

    def test_14_router_verifies_both_candidates(self):
        self.router.verify_models_available()
        self.assertEqual((self.normal.verify_calls, self.adult.verify_calls), (1, 1))

    def test_15_mode_status_has_three_states(self):
        self.assertEqual(adult_mode_status(False, False), "off")
        self.assertEqual(adult_mode_status(True, False), "available")
        self.assertEqual(adult_mode_status(True, True), "enabled")

    def test_16_environment_keeps_legacy_model_as_normal_fallback(self):
        values = {
            "PRITHI_LLM_BASE_URL": "http://127.0.0.1:11434/v1",
            "PRITHI_LLM_API_KEY": "ollama",
            "PRITHI_LLM_MODEL": "legacy:test",
        }
        with patch.dict(os.environ, values, clear=True):
            config = ModelRouterConfig.from_environment()
        self.assertEqual(config.normal_model, "legacy:test")
        self.assertEqual(config.adult_model, DEFAULT_ADULT_MODEL)

    def test_17_router_does_not_replace_brain_history_or_relationship_state(self):
        brain = FakeBrain()
        brain.history = ["old"]
        brain.relationship_state = {"trust": .4}
        with patch.object(self.router, "_loaded_prithi_models", return_value=[]):
            self.router.respond(brain, "hello")
        self.assertEqual(brain.history, ["old"])
        self.assertEqual(brain.relationship_state, {"trust": .4})


class AdultMemorySafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = MemoryStore(Path(self.temp.name) / "memory.db")
        self.user = stable_user_id("adult-routing-test-user")

    def tearDown(self):
        self.temp.cleanup()

    def test_age_confirmation_persists_but_is_minimal(self):
        self.store.set_adult_age_confirmed(self.user, True)
        reopened = MemoryStore(self.store.db_path)
        profile = reopened.get_profile(self.user)
        self.assertTrue(profile["adult_age_confirmed"])
        self.assertNotIn("adult_opt_in", profile)

    def test_explicit_adult_details_are_not_saved(self):
        self.assertFalse(self.store.add_memory(self.user, "preference", "User stated an intimate detail and sexual preference."))
        self.assertEqual(self.store.memory_count(self.user), 0)

    def test_explicit_adult_text_produces_no_memory_candidates(self):
        self.assertEqual(extract_memory_candidates("My favorite sexual preference is an intimate detail."), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
