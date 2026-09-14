import tempfile
import unittest
from pathlib import Path

from prithi_memory import (
    MemoryStore,
    extract_display_name,
    extract_memory_candidates,
    extract_profile_updates,
    stable_user_id,
)


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "memory.db"
        self.store = MemoryStore(self.path, max_memories=5)
        self.user = stable_user_id("browser-user-a")
        self.other = stable_user_id("browser-user-b")

    def tearDown(self):
        self.temp.cleanup()

    def test_database_initialization(self):
        self.assertTrue(self.path.is_file())

    def test_create_and_read_profile(self):
        profile = self.store.update_profile(self.user, preferred_language="bengali", display_name="Sayanika")
        self.assertEqual(profile["preferred_language"], "bengali")
        self.assertEqual(profile["display_name"], "Sayanika")

    def test_relationship_persistence_and_restart_reload(self):
        values = {"familiarity": .42, "trust": .31, "affection": .27, "playfulness": .20, "romantic_tension": .08}
        self.store.save_relationship(self.user, values, "warm", "caring")
        reopened = MemoryStore(self.path)
        restored = reopened.load_relationship(self.user)
        self.assertEqual(restored["familiarity"], .42)
        self.assertEqual(restored["current_emotion"], "warm")

    def test_user_isolation(self):
        self.store.add_memory(self.user, "preference", "Prefers tea.")
        self.assertEqual(self.store.memory_count(self.user), 1)
        self.assertEqual(self.store.memory_count(self.other), 0)

    def test_saved_preference_retrieval(self):
        self.store.add_memory(self.user, "preference", "Prefers tea over coffee.", .8)
        prompt = self.store.build_prompt(self.user, "coffee today")
        self.assertIn("Prefers tea over coffee", prompt)

    def test_unrelated_memory_is_not_injected(self):
        self.store.add_memory(self.user, "preference", "Prefers romantic poetry.", .8)
        prompt = self.store.build_prompt(self.user, "How much does two kilos weigh?")
        self.assertNotIn("romantic poetry", prompt)

    def test_no_duplicate_memory_spam(self):
        self.assertTrue(self.store.add_memory(self.user, "preference", "Prefers tea."))
        self.assertFalse(self.store.add_memory(self.user, "preference", "  PREFERS   TEA! "))
        self.assertEqual(self.store.memory_count(self.user), 1)

    def test_relationship_reset_preserves_profile_and_memories(self):
        self.store.update_profile(self.user, preferred_language="bengali")
        self.store.add_memory(self.user, "preference", "Prefers tea.")
        self.store.save_relationship(self.user, {"familiarity": .8, "trust": .8, "affection": .8, "playfulness": .8, "romantic_tension": .4})
        self.store.reset_relationship(self.user)
        self.assertEqual(self.store.load_relationship(self.user)["familiarity"], .15)
        self.assertEqual(self.store.get_profile(self.user)["preferred_language"], "bengali")
        self.assertEqual(self.store.memory_count(self.user), 1)

    def test_full_memory_deletion(self):
        self.store.add_memory(self.user, "preference", "Prefers tea.")
        self.store.save_relationship(self.user, {"familiarity": .4, "trust": .3, "affection": .3, "playfulness": .2, "romantic_tension": 0})
        self.store.delete_user_memory(self.user)
        self.assertEqual(self.store.get_profile(self.user), {})
        self.assertIsNone(self.store.load_relationship(self.user))
        self.assertEqual(self.store.memory_count(self.user), 0)

    def test_memory_limit_prunes_low_importance(self):
        for number in range(7):
            self.store.add_memory(self.user, "conversation_summary", f"summary {number}", number / 10)
        self.assertEqual(self.store.memory_count(self.user), 5)
        contents = {item["content"] for item in self.store.list_memories(self.user)}
        self.assertNotIn("summary 0", contents)
        self.assertNotIn("summary 1", contents)

    def test_sql_injection_content_is_data(self):
        attack = "tea'); DROP TABLE profiles; --"
        self.assertTrue(self.store.add_memory(self.user, "preference", attack))
        self.store.ensure_profile(self.other)
        self.assertEqual(self.store.memory_count(self.user), 1)

    def test_missing_memory_prompt_forbids_invention(self):
        prompt = self.store.build_prompt(self.user, "remember this?")
        self.assertIn("none", prompt)
        self.assertIn("Do not pretend", prompt)

    def test_sensitive_content_is_rejected(self):
        self.assertFalse(self.store.add_memory(self.user, "personal_fact", "My password is hunter2"))

    def test_conservative_extraction(self):
        candidates = extract_memory_candidates("আমার coffee-এর থেকে tea বেশি ভালো লাগে।")
        self.assertEqual([item.content for item in candidates], ["Prefers tea over coffee."])
        stt_variant = extract_memory_candidates("আমার কফির থেকে বেশি টি ভালো লাই")
        self.assertEqual([item.content for item in stt_variant], ["Prefers tea over coffee."])
        phonetic_stt_variant = extract_memory_candidates("আমি কাফির থেকে বেশি চাষ পছন্দ করি।")
        self.assertEqual([item.content for item in phonetic_stt_variant], ["Prefers tea over coffee."])
        self.assertEqual(extract_memory_candidates("আমি এখন বাইরে হাঁটছি।"), [])

    def test_display_name_extraction(self):
        self.assertEqual(extract_display_name("আমার নাম সায়নিকা।"), "সায়নিকা")

    def test_nickname_extraction_is_explicit_and_bounded(self):
        self.assertEqual(extract_display_name("আমাকে রুদ্র বলে ডাকো।"), "রুদ্র")
        self.assertEqual(extract_display_name("Please call me Avi."), "Avi")
        self.assertIsNone(extract_display_name("রুদ্র আজ এসেছিল।"))
        self.assertIsNone(extract_display_name("Call me " + "very " * 20))
        self.assertIsNone(extract_display_name("আমাকে কী নামে ডাকবে?"))

    def test_typed_language_and_banglish_profile_updates(self):
        self.assertEqual(extract_profile_updates("Reply in English please"), {"preferred_language": "english"})
        self.assertEqual(extract_profile_updates("আমার সাথে Banglish-এ কথা বলো"), {"preferred_language": "bengali"})

    def test_nickname_restart_persistence_and_user_isolation(self):
        updates = extract_profile_updates("আমাকে রুদ্র বলে ডাকো")
        self.store.update_profile(self.user, **updates)
        reopened = MemoryStore(self.path)
        self.assertEqual(reopened.get_profile(self.user)["display_name"], "রুদ্র")
        self.assertIsNone(reopened.ensure_profile(self.other)["display_name"])


if __name__ == "__main__":
    unittest.main()
