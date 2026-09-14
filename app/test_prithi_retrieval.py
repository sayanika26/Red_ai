import tempfile
import unittest
from pathlib import Path

from prithi_memory import MemoryStore, stable_user_id
from prithi_retrieval import KnowledgeRetriever, classify_knowledge, natural_status_line
from prithi_search import (
    SearchHistoryStore,
    SearchSource,
    evidence_from_sources,
    source_quality,
    ttl_for_query,
)


class FakeSearch:
    def __init__(self, batches):
        self.batches = list(batches)
        self.calls = []

    def search(self, query, limit=6):
        self.calls.append((query, limit))
        return self.batches.pop(0) if self.batches else []


OFFICIAL = [
    SearchSource("Official result", "https://example.gov/result", "The official current result is Alpha.", 1),
    SearchSource("Agency update", "https://agency.gov/update", "The current result is Alpha.", 1),
]


class RetrievalTests(unittest.TestCase):
    def test_ambiguous_current_affairs_question_clarifies(self):
        value = classify_knowledge("Who is the PM?")
        self.assertEqual(value.action, "clarify")
        self.assertIn("country", value.clarification.casefold())

    def test_wrong_us_office_title_is_corrected_before_search(self):
        value = classify_knowledge("Who is the PM of America?")
        self.assertEqual(value.action, "search")
        self.assertEqual(value.reason, "wrong_office_title")
        self.assertIn("President of the United States", value.query)

    def test_clarification_reply_completes_the_original_question(self):
        pending = "Who is the PM?"
        value = classify_knowledge("America", pending)
        self.assertEqual(value.action, "search")
        self.assertEqual(value.reason, "wrong_office_title")
        india = classify_knowledge("India", pending)
        self.assertEqual(india.action, "search")
        self.assertIn("India", india.query)

    def test_banglish_country_names_do_not_trigger_clarification(self):
        for text in ("Ekhon USA r president ke ache bolo to?", "India r PM ke ekhon?", "who is the president of america"):
            with self.subTest(text=text):
                self.assertEqual(classify_knowledge(text).action, "search")

    def test_conversational_office_questions_become_canonical_queries(self):
        banglish = classify_knowledge("Ekhon USA r president ke ache bolo to?")
        self.assertEqual(banglish.query, "current President of the United States")
        bengali = classify_knowledge("আমেরিকার বর্তমান প্রেসিডেন্ট কে?")
        self.assertEqual(bengali.query, "current President of the United States")
        india = classify_knowledge("Who is the prime minister of India right now?")
        self.assertEqual(india.query, "current Prime Minister of India")

    def test_non_office_questions_keep_their_original_query(self):
        value = classify_knowledge("What is the current price of Bitcoin?")
        self.assertEqual(value.query, "What is the current price of Bitcoin?")

    def test_bengali_speech_transcripts_tolerate_stt_spelling_variants(self):
        # Real Whisper output for "আমেরিকার বর্তমান প্রেসিডেন্ট কে?" misspells both words.
        value = classify_knowledge("এমেরিকার বর্তোমান প্রেসিডেন্ট কে")
        self.assertEqual(value.action, "search")
        self.assertEqual(value.query, "current President of the United States")

    def test_bare_verification_researches_the_previous_topic(self):
        value = classify_knowledge("Are you sure? Check again.", last_query="current President of the United States")
        self.assertEqual(value.action, "research_again")
        self.assertEqual(value.query, "current President of the United States")

    def test_verification_without_a_previous_topic_uses_the_utterance(self):
        self.assertEqual(classify_knowledge("Are you sure?").query, "Are you sure?")

    def test_bare_pronoun_us_still_asks_for_the_country(self):
        self.assertEqual(classify_knowledge("Can you tell us who the PM is?").action, "clarify")

    def test_second_clarification_is_never_requested(self):
        self.assertEqual(classify_knowledge("hmm", "Who is the PM?").action, "search")

    def test_office_correction_is_explained_in_the_prompt(self):
        result = KnowledgeRetriever(FakeSearch([OFFICIAL])).retrieve("Who is the PM of America?")
        self.assertIn("not a Prime Minister", result.prompt())

    def test_fast_moving_facts_get_a_shorter_cache_ttl(self):
        self.assertLess(ttl_for_query("live cricket score"), ttl_for_query("who is the president of India"))
        self.assertEqual(ttl_for_query("why do leaves look green"), 900)

    def test_current_fact_searches_but_stable_conversation_stays_local(self):
        self.assertEqual(classify_knowledge("What is the current cricket score?").action, "search")
        self.assertEqual(classify_knowledge("Why do leaves look green?").action, "local")
        self.assertEqual(classify_knowledge("I feel lonely today").action, "local")

    def test_explicit_verification_runs_second_authoritative_search(self):
        provider = FakeSearch([OFFICIAL[:1], OFFICIAL[1:]])
        result = KnowledgeRetriever(provider).retrieve("Please verify the current result")
        self.assertEqual(result.decision.action, "research_again")
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(result.evidence.retry_count, 1)

    def test_conflicting_sources_produce_honest_unknown(self):
        conflict = [
            SearchSource("A", "https://a.gov/x", "Alice is the current office holder today.", 1),
            SearchSource("B", "https://b.gov/x", "Alice is not the current office holder today.", 1),
        ]
        provider = FakeSearch([conflict, conflict])
        result = KnowledgeRetriever(provider).retrieve("current office holder")
        self.assertEqual(result.decision.action, "unknown")
        self.assertIn("do not invent", result.prompt())

    def test_no_reliable_result_is_unknown(self):
        result = KnowledgeRetriever(FakeSearch([[], []])).retrieve("latest obscure event")
        self.assertEqual(result.decision.action, "unknown")

    def test_search_status_preserves_language_and_varies_by_seed(self):
        self.assertRegex(natural_status_line("search", "bengali", "one"), r"[\u0980-\u09ff]")
        self.assertRegex(natural_status_line("search", "hindi", "two"), r"[\u0900-\u097f]")
        self.assertTrue(natural_status_line("search", "english", "three").endswith((".", "it.")))

    def test_source_ranking_prefers_primary_sources(self):
        self.assertLess(source_quality("https://data.gov/report"), source_quality("https://random.example/blog"))

    def test_search_cache_is_separate_from_personal_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.db"
            memory = MemoryStore(path)
            cache = SearchHistoryStore(path)
            evidence = evidence_from_sources("current result", OFFICIAL)
            cache.put(evidence)
            self.assertIsNotNone(cache.get("current result"))
            self.assertEqual(memory.memory_count(stable_user_id("person")), 0)


if __name__ == "__main__":
    unittest.main()
