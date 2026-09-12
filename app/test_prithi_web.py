import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from prithi_web import WebConfig, create_app
from prithi_brain import RelationshipState
from prithi_memory import MemoryCandidate, MemoryStore, stable_user_id


TOKEN = "test-token-not-a-real-secret"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def write_wav(path: Path, frames: int = 1600) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * frames)


def fake_converter(source: Path, destination: Path, max_seconds: float):
    del source, max_seconds
    write_wav(destination)
    return 0.01, 0.1


class FakePipeline:
    def __init__(self, status="SUCCESS"):
        self.status = status
        self.turns = []
        self.reset_calls = 0
        self.clear_calls = 0
        self.last_memory_context = None
        self.brain = SimpleNamespace(
            relationship_state=RelationshipState(),
            current_emotion="neutral",
            previous_emotion="neutral",
        )

    def commit_brain(self):
        self.brain.previous_emotion = self.brain.current_emotion
        self.brain.current_emotion = "warm"
        self.brain.relationship_state.apply(familiarity=.015, trust=.01, affection=.01)

    def process_audio(self, path, language, memory_context=None):
        self.turns.append((str(path), language))
        self.last_memory_context = memory_context
        if self.status == "STT_EMPTY":
            return {"status": "STT_EMPTY", "transcript": "", "stt": {"text": ""}}
        if self.status == "BRAIN_FAILED":
            return {"status": "BRAIN_FAILED", "transcript": "আজ কেমন আছো?", "stt": {"text": "আজ কেমন আছো?"}}
        self.commit_brain()
        handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        output = Path(handle.name)
        handle.close()
        write_wav(output)
        return {
            "status": "SUCCESS",
            "transcript": "আজ কেমন আছো?",
            "stt": {"detected_language": "bn", "transcription_time": 0.2},
            "brain": {
                "reply": "আমি ভালো আছি।",
                "language": "bengali",
                "emotion": "warm",
                "voice_style": {"warmth": 0.8},
                "generation_time": 0.3,
            },
            "voice": {
                "output_path": str(output),
                "generation_time": 0.4,
                "duration": 0.1,
                "fallback_occurred": False,
            },
        }

    def transcribe_only(self, path, language):
        self.turns.append((str(path), language))
        if self.status == "STT_EMPTY":
            return {"text": "", "detected_language": "bn", "transcription_time": 0.2, "model_load_time": 0.0, "model_reused": True}
        return {"text": "আজ কেমন আছো?", "detected_language": "bn", "transcription_time": 0.2, "model_load_time": 0.0, "model_reused": True}

    def respond_only(self, transcript, preferred_reply_language=None, memory_context=None):
        del transcript
        self.last_memory_context = memory_context
        self.commit_brain()
        return {
            "reply": "আমি ভালো আছি।",
            "language": "bengali",
            "emotion": "warm",
            "voice_style": {"warmth": 0.8},
            "generation_time": 0.3,
        }

    def synthesize_only(self, brain):
        del brain
        handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        output = Path(handle.name)
        handle.close()
        write_wav(output)
        return {
            "output_path": str(output),
            "generation_time": 0.4,
            "duration": 0.1,
            "fallback_occurred": False,
        }

    def reset(self):
        self.turns.clear()
        self.reset_calls += 1

    def clear_conversation(self):
        self.turns.clear()
        self.clear_calls += 1

    def reset_relationship(self):
        self.brain.relationship_state = RelationshipState()
        self.brain.current_emotion = "neutral"
        self.brain.previous_emotion = "neutral"


class Factory:
    def __init__(self, status="SUCCESS"):
        self.status = status
        self.instances = []

    def __call__(self):
        instance = FakePipeline(self.status)
        self.instances.append(instance)
        return instance


class PrithiWebTests(unittest.TestCase):
    def make_client(self, factory=None, **config_overrides):
        factory = factory or Factory()
        config = WebConfig(access_token=TOKEN, **config_overrides)
        temp = tempfile.TemporaryDirectory()
        memory = MemoryStore(Path(temp.name) / "memory.db")
        app = create_app(
            config=config,
            pipeline_factory=factory,
            health_checker=lambda: {"ollama": True, "stt": True, "tts_configured": True},
            converter=fake_converter,
            memory_store=memory,
        )
        app.state.test_memory_directory = temp
        return TestClient(app), factory, app

    def prime(self, client):
        self.assertEqual(client.get("/").status_code, 200)

    def turn(self, client, content=b"audio", language="bengali"):
        return client.post(
            "/api/voice-turn",
            headers=HEADERS,
            files={"audio": ("untrusted-name.webm", content, "audio/webm")},
            data={"language": language},
        )

    def stream_turn(self, client, content=b"audio", language="bengali"):
        return client.post(
            "/api/voice-turn-stream",
            headers=HEADERS,
            files={"audio": ("recording.webm", content, "audio/webm")},
            data={"language": language},
        )

    def test_health_endpoint(self):
        client, _, _ = self.make_client()
        response = client.get("/api/health", headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "version": "1.0.0", "ollama": True, "stt": True, "tts_configured": True})

    def test_missing_token_rejected(self):
        client, _, _ = self.make_client()
        self.assertEqual(client.get("/api/health").status_code, 401)

    def test_invalid_token_rejected(self):
        client, _, _ = self.make_client()
        self.assertEqual(client.get("/api/health", headers={"Authorization": "Bearer wrong"}).status_code, 401)

    def test_valid_token_accepted(self):
        client, _, _ = self.make_client()
        self.assertEqual(client.get("/api/health", headers=HEADERS).status_code, 200)

    def test_invalid_upload_rejected(self):
        client, _, _ = self.make_client()
        response = client.post(
            "/api/voice-turn",
            headers=HEADERS,
            files={"audio": ("attack.txt", b"bad", "text/plain")},
            data={"language": "bengali"},
        )
        self.assertEqual(response.status_code, 415)

    def test_internal_failure_hides_stack_trace(self):
        class ExplodingPipeline(FakePipeline):
            def process_audio(self, path, language, memory_context=None):
                raise RuntimeError("private implementation detail")

        client, _, _ = self.make_client(lambda: ExplodingPipeline())
        self.prime(client)
        response = self.turn(client)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Internal Prithi service error"})
        self.assertNotIn("Traceback", response.text)
        self.assertNotIn("private implementation detail", response.text)

    def test_empty_stt_result(self):
        client, _, _ = self.make_client(Factory("STT_EMPTY"))
        self.prime(client)
        self.assertEqual(self.turn(client).status_code, 422)

    def test_successful_mocked_voice_turn(self):
        client, _, _ = self.make_client()
        self.prime(client)
        response = self.turn(client)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["detected_language"], "bn")
        self.assertEqual(body["emotion"], "warm")
        self.assertTrue(body["audio_url"].startswith("/api/audio/"))
        self.assertNotIn("/tmp/", str(body))

    def test_per_session_history_isolation(self):
        factory = Factory()
        client_a, _, _ = self.make_client(factory)
        client_b = TestClient(client_a.app)
        self.prime(client_a)
        self.prime(client_b)
        self.assertEqual(self.turn(client_a).status_code, 200)
        self.assertEqual(self.turn(client_b).status_code, 200)
        self.assertEqual(len(factory.instances), 2)
        self.assertEqual(len(factory.instances[0].turns), 1)
        self.assertEqual(len(factory.instances[1].turns), 1)

    def test_reset_only_current_session(self):
        factory = Factory()
        client_a, _, _ = self.make_client(factory)
        client_b = TestClient(client_a.app)
        self.prime(client_a)
        self.prime(client_b)
        self.turn(client_a)
        self.turn(client_b)
        self.assertEqual(client_a.post("/api/reset", headers=HEADERS).status_code, 200)
        self.assertEqual(factory.instances[0].clear_calls, 1)
        self.assertEqual(factory.instances[1].clear_calls, 0)

    def test_safe_audio_file_retrieval(self):
        client, _, _ = self.make_client()
        other = TestClient(client.app)
        self.prime(client)
        self.prime(other)
        audio_url = self.turn(client).json()["audio_url"]
        response = client.get(audio_url, headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/wav")
        self.assertEqual(other.get(audio_url, headers=HEADERS).status_code, 404)

    def test_path_traversal_rejected(self):
        client, _, _ = self.make_client()
        self.prime(client)
        response = client.get("/api/audio/..%2F..%2Fetc%2Fpasswd", headers=HEADERS)
        self.assertEqual(response.status_code, 404)

    def test_recording_file_size_limit(self):
        client, _, _ = self.make_client(max_upload_bytes=4)
        self.prime(client)
        self.assertEqual(self.turn(client, content=b"12345").status_code, 413)

    def test_streaming_progress_event_order(self):
        client, _, _ = self.make_client()
        self.prime(client)
        response = self.stream_turn(client)
        self.assertEqual(response.status_code, 200)
        events = [
            __import__("json").loads(line[6:])["event"]
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        self.assertEqual(events, ["language", "transcript", "thinking", "reply", "audio_ready"])
        self.assertLess(events.index("transcript"), events.index("reply"))
        self.assertLess(events.index("reply"), events.index("audio_ready"))
        reply_event = next(
            __import__("json").loads(line[6:])
            for line in response.text.splitlines()
            if line.startswith("data: ") and '"event": "reply"' in line
        )
        self.assertIn("memory_saved_count", reply_event)

    def test_streaming_empty_stt_stops_before_reply(self):
        client, _, _ = self.make_client(Factory("STT_EMPTY"))
        self.prime(client)
        response = self.stream_turn(client)
        self.assertIn('"event": "error"', response.text)
        self.assertNotIn('"event": "reply"', response.text)

    def test_stream_temporary_directory_is_cleaned(self):
        seen = []

        def tracking_converter(source, destination, max_seconds):
            seen.append(destination.parent)
            return fake_converter(source, destination, max_seconds)

        factory = Factory()
        app = create_app(
            config=WebConfig(access_token=TOKEN),
            pipeline_factory=factory,
            health_checker=lambda: {"ollama": True, "stt": True, "tts_configured": True},
            converter=tracking_converter,
        )
        client = TestClient(app)
        self.prime(client)
        self.assertEqual(self.stream_turn(client).status_code, 200)
        self.assertTrue(seen)
        self.assertFalse(seen[0].exists())

    def test_frontend_stop_cancels_fetch_and_audio(self):
        source = (Path(__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("activeTurnController?.abort()", source)
        self.assertIn("responseAudio.pause()", source)

    def test_reply_displays_before_audio_and_generating_status(self):
        source = (Path(__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('setStatus("Generating voice", "thinking")', source)
        self.assertLess(source.index('replyEl.textContent = event.text'), source.index('await prepareAndPlay(event.audio_url)'))

    def test_memory_api_requires_authentication(self):
        client, _, _ = self.make_client()
        self.prime(client)
        self.assertEqual(client.get("/api/memory").status_code, 401)
        self.assertEqual(client.get("/api/memory", headers={"Authorization": "Bearer wrong"}).status_code, 401)
        self.assertEqual(client.get("/api/memory", headers=HEADERS).status_code, 200)

    def test_clear_conversation_preserves_saved_memory_and_relationship(self):
        client, _, app = self.make_client()
        self.prime(client)
        self.assertEqual(self.stream_turn(client).status_code, 200)
        identity = client.cookies.get("prithi_user")
        user_id = stable_user_id(identity)
        app.state.memory.add_memory(user_id, "preference", "Prefers tea.")
        before = app.state.memory.load_relationship(user_id)
        self.assertEqual(client.post("/api/memory/reset-conversation", headers=HEADERS).status_code, 200)
        self.assertEqual(app.state.memory.memory_count(user_id), 1)
        self.assertEqual(app.state.memory.load_relationship(user_id)["familiarity"], before["familiarity"])

    def test_relationship_reset_preserves_profile_and_items(self):
        client, _, app = self.make_client()
        self.prime(client)
        self.stream_turn(client)
        user_id = stable_user_id(client.cookies.get("prithi_user"))
        app.state.memory.add_memory(user_id, "preference", "Prefers tea.")
        response = client.post("/api/memory/reset-relationship", headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(app.state.memory.load_relationship(user_id)["familiarity"], .15)
        self.assertEqual(app.state.memory.memory_count(user_id), 1)
        self.assertEqual(app.state.memory.get_profile(user_id)["preferred_language"], "bengali")

    def test_delete_saved_memory_is_scoped_to_current_user(self):
        client_a, _, app = self.make_client()
        client_b = TestClient(client_a.app)
        self.prime(client_a)
        self.prime(client_b)
        user_a = stable_user_id(client_a.cookies.get("prithi_user"))
        user_b = stable_user_id(client_b.cookies.get("prithi_user"))
        app.state.memory.add_memory(user_a, "preference", "Prefers tea.")
        app.state.memory.add_memory(user_b, "preference", "Prefers coffee.")
        self.assertEqual(client_a.delete("/api/memory", headers=HEADERS).status_code, 200)
        self.assertEqual(app.state.memory.memory_count(user_a), 0)
        self.assertEqual(app.state.memory.memory_count(user_b), 1)

    def test_failed_turn_does_not_persist_relationship(self):
        for failure, expected_status in (("STT_EMPTY", 422), ("BRAIN_FAILED", 502)):
            with self.subTest(failure=failure):
                client, _, app = self.make_client(Factory(failure))
                self.prime(client)
                self.assertEqual(self.turn(client).status_code, expected_status)
                user_id = stable_user_id(client.cookies.get("prithi_user"))
                self.assertIsNone(app.state.memory.load_relationship(user_id))

    def test_memory_extraction_failure_does_not_break_turn(self):
        client, _, app = self.make_client()
        self.prime(client)
        app.state.memory.add_memory = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("test failure"))
        with patch("prithi_web.extract_memory_candidates", return_value=[MemoryCandidate("preference", "Prefers tea.")]):
            self.assertEqual(self.turn(client).status_code, 200)

    def test_restart_restores_same_user_but_not_other_user(self):
        client, _, app = self.make_client()
        self.prime(client)
        self.assertEqual(self.stream_turn(client).status_code, 200)
        identity = client.cookies.get("prithi_user")
        user_id = stable_user_id(identity)
        app.state.memory.add_memory(user_id, "preference", "Prefers tea.")
        memory = app.state.memory

        restarted = create_app(
            config=WebConfig(access_token=TOKEN),
            pipeline_factory=Factory(),
            health_checker=lambda: {"ollama": True, "stt": True, "tts_configured": True},
            converter=fake_converter,
            memory_store=memory,
        )
        same_user = TestClient(restarted)
        same_user.cookies.set("prithi_user", identity)
        self.assertEqual(same_user.get("/").status_code, 200)
        restored = same_user.get("/api/memory", headers=HEADERS).json()
        self.assertTrue(restored["relationship_restored"])
        self.assertEqual(restored["saved_memory_count"], 1)

        other_user = TestClient(restarted)
        self.prime(other_user)
        isolated = other_user.get("/api/memory", headers=HEADERS).json()
        self.assertEqual(isolated["saved_memory_count"], 0)
        self.assertIsNone(isolated["relationship"])

    def test_stable_browser_header_restores_when_proxy_cookie_is_lost(self):
        client, _, app = self.make_client()
        identity = "A" * 43
        headers = {**HEADERS, "X-Prithi-User": identity}
        self.assertEqual(client.get("/api/memory", headers=headers).status_code, 200)
        user_id = stable_user_id(identity)
        app.state.memory.add_memory(user_id, "preference", "Prefers tea.")
        app.state.memory.save_relationship(user_id, {"familiarity": .4, "trust": .3, "affection": .2, "playfulness": .2, "romantic_tension": 0})
        cookie_free = TestClient(client.app)
        restored = cookie_free.get("/api/memory", headers=headers).json()
        self.assertEqual(restored["saved_memory_count"], 1)
        self.assertEqual(restored["relationship"]["familiarity"], .4)

    def test_adult_mode_api_requires_authentication(self):
        client, _, _ = self.make_client()
        self.prime(client)
        self.assertEqual(client.get("/api/adult-mode").status_code, 401)
        self.assertEqual(client.post("/api/adult-mode/enable", json={"enabled": True}).status_code, 401)

    def test_adult_mode_defaults_off(self):
        client, _, _ = self.make_client()
        self.prime(client)
        mode = client.get("/api/adult-mode", headers=HEADERS).json()
        self.assertEqual(mode["status"], "off")
        self.assertEqual(mode["conversation_mode"], "normal")
        self.assertFalse(mode["age_confirmed"])

    def test_enable_requires_prior_age_confirmation(self):
        client, _, _ = self.make_client()
        self.prime(client)
        response = client.post("/api/adult-mode/enable", headers=HEADERS, json={"enabled": True})
        self.assertEqual(response.status_code, 403)

    def test_age_confirmation_and_opt_in_are_separate_actions(self):
        client, _, _ = self.make_client()
        self.prime(client)
        confirmed = client.post("/api/adult-mode/confirm-age", headers=HEADERS, json={"confirmed": True}).json()
        self.assertEqual(confirmed["status"], "available")
        self.assertFalse(confirmed["adult_opt_in"])
        enabled = client.post("/api/adult-mode/enable", headers=HEADERS, json={"enabled": True}).json()
        self.assertEqual(enabled["status"], "enabled")
        self.assertEqual(enabled["conversation_mode"], "adult")
        self.assertIn("qwen3-14b-abliterated", enabled["selected_model"])

    def test_disable_immediately_returns_to_normal(self):
        client, _, _ = self.make_client()
        self.prime(client)
        client.post("/api/adult-mode/confirm-age", headers=HEADERS, json={"confirmed": True})
        client.post("/api/adult-mode/enable", headers=HEADERS, json={"enabled": True})
        disabled = client.post("/api/adult-mode/disable", headers=HEADERS).json()
        self.assertEqual(disabled["conversation_mode"], "normal")
        self.assertEqual(disabled["selected_model"], "gemma3:12b")

    def test_adult_opt_in_is_session_scoped(self):
        client, _, _ = self.make_client()
        self.prime(client)
        client.post("/api/adult-mode/confirm-age", headers=HEADERS, json={"confirmed": True})
        client.post("/api/adult-mode/enable", headers=HEADERS, json={"enabled": True})
        identity = client.cookies.get("prithi_user")
        fresh = TestClient(client.app)
        fresh.cookies.set("prithi_user", identity)
        fresh.get("/")
        mode = fresh.get("/api/adult-mode", headers=HEADERS).json()
        self.assertTrue(mode["age_confirmed"])
        self.assertFalse(mode["adult_opt_in"])
        self.assertEqual(mode["status"], "available")

    def test_restart_persists_age_but_resets_adult_mode(self):
        client, _, app = self.make_client()
        self.prime(client)
        client.post("/api/adult-mode/confirm-age", headers=HEADERS, json={"confirmed": True})
        client.post("/api/adult-mode/enable", headers=HEADERS, json={"enabled": True})
        identity = client.cookies.get("prithi_user")
        restarted = create_app(
            config=WebConfig(access_token=TOKEN), pipeline_factory=Factory(),
            health_checker=lambda: {"ollama": True, "stt": True, "tts_configured": True},
            converter=fake_converter, memory_store=app.state.memory,
        )
        fresh = TestClient(restarted)
        fresh.cookies.set("prithi_user", identity)
        fresh.get("/")
        mode = fresh.get("/api/adult-mode", headers=HEADERS).json()
        self.assertTrue(mode["age_confirmed"])
        self.assertFalse(mode["adult_opt_in"])

    def test_deleting_memory_also_removes_age_confirmation(self):
        client, _, _ = self.make_client()
        self.prime(client)
        client.post("/api/adult-mode/confirm-age", headers=HEADERS, json={"confirmed": True})
        self.assertEqual(client.delete("/api/memory", headers=HEADERS).status_code, 200)
        mode = client.get("/api/adult-mode", headers=HEADERS).json()
        self.assertFalse(mode["age_confirmed"])
        self.assertFalse(mode["adult_opt_in"])

    def test_frontend_has_explicit_age_and_opt_in_controls(self):
        html = (Path(__file__).parent / "web" / "index.html").read_text(encoding="utf-8")
        script = (Path(__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("I confirm that I am 18 or older", html)
        self.assertIn("Enable adult mode for this session", html)
        self.assertIn("/api/adult-mode/confirm-age", script)
        self.assertIn("/api/adult-mode/enable", script)

    def test_continuous_ui_keeps_manual_mode_as_default(self):
        html = (Path(__file__).parent / "web" / "index.html").read_text(encoding="utf-8")
        script = (Path(__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="manual-mode"', html)
        self.assertIn('id="conversation-mode"', html)
        self.assertIn('id="conversation-toggle"', html)
        self.assertIn('selectInputMode("manual")', script)
        self.assertIn("async function startRecording()", script)

    def test_continuous_state_machine_has_guarded_transitions(self):
        source = (Path(__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
        for state in ("IDLE", "WAITING_FOR_SPEECH", "RECORDING_SPEECH", "PROCESSING", "PLAYING_REPLY", "PAUSED", "ERROR"):
            self.assertIn(f'{state}: "{state}"', source)
        self.assertIn("CONVERSATION_TRANSITIONS", source)
        self.assertIn("Ignored invalid conversation transition", source)

    def test_continuous_vad_defaults_are_conservative(self):
        source = (Path(__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("silenceMs: 900", source)
        self.assertIn("minSpeechMs: 500", source)
        self.assertIn("maxTurnMs: 60000", source)
        self.assertIn("postPlaybackGuardMs: 350", source)
        self.assertIn("window.PRITHI_VAD_CONFIG", source)

    def test_continuous_vad_does_not_record_or_upload_silence(self):
        source = (Path(__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("aboveStartFrames >= VAD_CONFIG.startFrames", source)
        self.assertIn("beginConversationTurn(now)", source)
        self.assertIn("shouldSubmitConversationTurn()", source)
        self.assertIn("voicedDurationMs >= VAD_CONFIG.minSpeechMs", source)

    def test_continuous_vad_ends_on_silence_or_max_duration(self):
        source = (Path(__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("now - lastSpeechAt >= VAD_CONFIG.silenceMs", source)
        self.assertIn("now - speechStartedAt >= VAD_CONFIG.maxTurnMs", source)
        self.assertIn("finishingConversationTurn", source)

    def test_continuous_mode_reuses_one_microphone_stream(self):
        source = (Path(__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
        start = source.index("async function startConversation()")
        stop = source.index("async function stopConversation", start)
        body = source[start:stop]
        self.assertEqual(body.count("getUserMedia"), 2)  # capability check plus one authorization call
        self.assertIn("conversationVadTick(conversationEpoch)", body)
        self.assertNotIn("getUserMedia", source[source.index("function beginConversationTurn"):start])

    def test_continuous_mode_requests_echo_protection(self):
        source = (Path(__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("echoCancellation: true", source)
        self.assertIn("noiseSuppression: true", source)
        self.assertIn("autoGainControl: true", source)

    def test_continuous_processing_blocks_second_turn(self):
        source = (Path(__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("conversationState === ConversationState.WAITING_FOR_SPEECH && !activeTurnController", source)
        self.assertIn("finishingConversationTurn || conversationState !== ConversationState.RECORDING_SPEECH", source)

    def test_continuous_mic_is_inactive_during_playback(self):
        source = (Path(__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("transitionConversation(ConversationState.PLAYING_REPLY)", source)
        self.assertIn("conversationState === ConversationState.WAITING_FOR_SPEECH", source)
        self.assertIn("scheduleConversationListening", source)

    def test_stop_conversation_releases_microphone_tracks(self):
        source = (Path(__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
        stop = source[source.index("async function stopConversation"):source.index("async function startRecording")]
        self.assertIn("stream?.getTracks().forEach((track) => track.stop())", stop)
        self.assertIn("conversationAudioContext.close()", stop)

    def test_continuous_failure_recovers_to_listening(self):
        source = (Path(__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
        recover = source[source.index("function recoverConversation"):source.index("function beginConversationTurn")]
        self.assertIn("I couldn't catch that. Try again.", recover)
        self.assertIn("ConversationState.WAITING_FOR_SPEECH", recover)

    def test_continuous_turn_preserves_language_session_and_adult_routes(self):
        source = (Path(__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('form.append("language", languageEl.value)', source)
        self.assertIn('"X-Prithi-User": browserIdentity()', source)
        self.assertIn("/api/adult-mode", source)
        self.assertIn('fetch("/api/voice-turn-stream"', source)

    def test_visibility_loss_pauses_continuous_mode(self):
        source = (Path(__file__).parent / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('document.addEventListener("visibilitychange"', source)
        self.assertIn("stopConversation({ paused: true })", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
