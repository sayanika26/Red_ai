"""End-to-end checks that v3.2 search intelligence reaches both text and voice turns."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from prithi_memory import MemoryStore
from prithi_retrieval import KnowledgeRetriever
from prithi_search import SearchHistoryStore, SearchSource
from prithi_web import WebConfig, create_app
from test_prithi_web import HEADERS, TOKEN, FakePipeline, fake_converter


CURRENT_FACT_QUESTION = "What is the current cricket score?"


class SearchingVoicePipeline(FakePipeline):
    """Speaks a question that must be searched, so voice turns exercise retrieval."""

    def transcribe_only(self, path, language):
        result = super().transcribe_only(path, language)
        result["text"] = CURRENT_FACT_QUESTION
        return result


class Factory:
    def __init__(self, status="SUCCESS", pipeline=FakePipeline):
        self.status, self.pipeline, self.instances = status, pipeline, []

    def __call__(self):
        instance = self.pipeline(self.status)
        self.instances.append(instance)
        return instance


CURRENT = [
    SearchSource("Official register", "https://example.gov/holder", "The current office holder is Alpha.", 1),
    SearchSource("Reuters", "https://reuters.com/holder", "Alpha currently holds the office.", 2),
]
CONFLICT = [
    SearchSource("Gazette", "https://a.gov/x", "Alice is the current office holder today.", 1),
    SearchSource("Ministry", "https://b.gov/x", "Alice is not the current office holder today.", 1),
]


class ScriptedSearch:
    """Deterministic provider so tests never touch the network."""

    def __init__(self, sources):
        self.sources = list(sources)
        self.calls = []

    def search(self, query, limit=6):
        self.calls.append(query)
        return list(self.sources)


class SearchIntegrationTests(unittest.TestCase):
    def make_client(self, sources=CURRENT, factory=None, **config_overrides):
        factory = factory or Factory()
        config = WebConfig(access_token=TOKEN, **config_overrides)
        temp = tempfile.TemporaryDirectory()
        memory = MemoryStore(Path(temp.name) / "memory.db")
        provider = ScriptedSearch(sources)
        # Cache shares the database file on purpose: the tables must stay separate.
        cache = SearchHistoryStore(memory.db_path, ttl_seconds=900)
        app = create_app(
            config=config,
            pipeline_factory=factory,
            health_checker=lambda: {"ollama": True, "stt": True, "tts_configured": True},
            converter=fake_converter,
            memory_store=memory,
            knowledge_retriever=KnowledgeRetriever(provider, cache),
        )
        app.state.test_memory_directory = temp
        client = TestClient(app)
        self.assertEqual(client.get("/").status_code, 200)
        return client, factory, provider, memory

    def say(self, client, text, language="bengali"):
        response = client.post(
            "/api/text-turn",
            headers=HEADERS,
            data={"text": text, "language": language, "voice_reply": "false"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    # --- routing ------------------------------------------------------

    def test_current_fact_triggers_search_on_typed_turn(self):
        client, _, provider, _ = self.make_client()
        payload = self.say(client, "What is the current cricket score?")
        self.assertEqual(payload["knowledge_action"], "search")
        self.assertGreater(payload["search_source_count"], 0)
        self.assertTrue(provider.calls)

    def test_stable_question_stays_local_without_searching(self):
        client, _, provider, _ = self.make_client()
        payload = self.say(client, "Why do leaves look green?")
        self.assertEqual(payload["knowledge_action"], "local")
        self.assertEqual(provider.calls, [])

    def test_casual_conversation_never_searches(self):
        client, _, provider, _ = self.make_client()
        payload = self.say(client, "আজ আমার মন খারাপ")
        self.assertEqual(payload["knowledge_action"], "local")
        self.assertEqual(provider.calls, [])

    def test_typed_turn_feeds_compact_evidence_not_raw_pages(self):
        client, factory, provider, _ = self.make_client()
        self.say(client, "What is the current cricket score?")
        self.assertTrue(provider.calls)
        prompt = factory.instances[0].last_adaptive_context
        self.assertIn("Knowledge action: search", prompt)
        self.assertIn("example.gov", prompt)
        self.assertLess(len(prompt), 4000, "evidence must stay a compact summary")

    def test_voice_turn_searches_and_streams_status_states(self):
        client, factory, provider, _ = self.make_client(factory=Factory(pipeline=SearchingVoicePipeline))
        response = client.post(
            "/api/voice-turn-stream",
            headers=HEADERS,
            files={"audio": ("recording.webm", b"audio", "audio/webm")},
            data={"language": "bengali"},
        )
        self.assertEqual(response.status_code, 200)
        events = [
            json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
        ]
        names = [item["event"] for item in events]
        self.assertIn("searching", names)
        self.assertIn("reading", names)
        self.assertLess(names.index("searching"), names.index("reading"))
        self.assertLess(names.index("reading"), names.index("reply"))
        status = next(item for item in events if item["event"] == "searching")
        self.assertTrue(status["text"].strip(), "an interim status line must be spoken")
        self.assertTrue(provider.calls, "the voice path must reach the search provider")
        self.assertIn("Knowledge action: search", factory.instances[0].last_adaptive_context)

    # --- ambiguity and terminology ------------------------------------

    def test_ambiguous_office_asks_one_clarification_then_answers(self):
        client, factory, provider, _ = self.make_client()
        first = self.say(client, "Who is the PM?")
        self.assertEqual(first["knowledge_action"], "clarify")
        self.assertEqual(provider.calls, [])
        self.assertIn("clarify", factory.instances[0].last_adaptive_context.casefold())

        second = self.say(client, "America")
        self.assertEqual(second["knowledge_action"], "search")
        self.assertTrue(provider.calls)
        prompt = factory.instances[0].last_adaptive_context
        self.assertIn("President", prompt)
        self.assertIn("not a Prime Minister", prompt)

    def test_clarification_is_asked_only_once(self):
        client, _, _, _ = self.make_client()
        self.say(client, "Who is the PM?")
        self.assertEqual(self.say(client, "hmm")["knowledge_action"], "search")

    # --- retry, conflict and honesty ----------------------------------

    def test_explicit_verification_runs_a_second_search(self):
        client, _, provider, _ = self.make_client()
        payload = self.say(client, "Are you sure? Please verify the current result")
        self.assertEqual(payload["knowledge_action"], "research_again")
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(payload["search_retry_count"], 1)

    def test_conflicting_sources_admit_uncertainty_instead_of_answering(self):
        client, factory, _, _ = self.make_client(sources=CONFLICT)
        payload = self.say(client, "Who is the current office holder?")
        self.assertEqual(payload["knowledge_action"], "unknown")
        self.assertIn("do not invent", factory.instances[0].last_adaptive_context)

    def test_failed_search_returns_honest_uncertainty(self):
        client, factory, _, _ = self.make_client(sources=[])
        payload = self.say(client, "What is the latest obscure election result?")
        self.assertEqual(payload["knowledge_action"], "unknown")
        prompt = factory.instances[0].last_adaptive_context
        self.assertIn("Admit uncertainty", prompt)
        self.assertIn("do not invent an answer", prompt)

    # --- personality, memory and gating -------------------------------

    def test_personality_and_language_survive_a_searched_turn(self):
        client, factory, _, _ = self.make_client()
        payload = self.say(client, "What is the current cricket score?")
        self.assertEqual(payload["language"], "bengali")
        prompt = factory.instances[0].last_adaptive_context
        self.assertIn("keep the current Prithi language and tone", prompt)
        self.assertIn("Adaptive response state:", prompt)
        self.assertIn("\"mood\"", prompt)

    def test_search_results_never_become_personal_memory(self):
        client, _, _, memory = self.make_client()
        payload = self.say(client, "What is the current cricket score?")
        self.assertEqual(payload["knowledge_action"], "search")
        with sqlite3.connect(memory.db_path) as db:
            personal = db.execute("SELECT count(*) FROM memory_items WHERE content LIKE '%example.gov%'").fetchone()[0]
            cached = db.execute("SELECT count(*) FROM retrieval_cache WHERE evidence_json LIKE '%example.gov%'").fetchone()[0]
        self.assertEqual(personal, 0, "retrieved facts must never land in personal memory")
        self.assertEqual(cached, 1, "retrieved facts belong in the TTL search cache")

    def test_adult_mode_stays_gated_while_search_is_available(self):
        client, _, _, _ = self.make_client()
        blocked = client.post("/api/adult-mode/enable", headers=HEADERS, json={"enabled": True})
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(self.say(client, "What is the current cricket score?")["knowledge_action"], "search")
        self.assertEqual(client.get("/api/adult-mode", headers=HEADERS).json()["status"], "off")

    def test_silence_followup_is_offered_at_most_once(self):
        client, _, _, _ = self.make_client(silence_followup_seconds=0.01)
        self.say(client, "Why do leaves look green?")
        messages = [client.get("/api/follow-up", headers=HEADERS).json()["message"] for _ in range(3)]
        self.assertLessEqual(len([item for item in messages if item]), 1)


if __name__ == "__main__":
    unittest.main()
