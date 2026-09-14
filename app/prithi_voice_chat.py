import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from llm_provider import OpenAICompatibleBackend
from prithi_brain import PrithiBrain
from prithi_chat import load_local_env
from prithi_mic import (
    MicrophoneUnavailableError,
    PlaybackUnavailableError,
    PushToTalkRecorder,
    RecordingConfig,
    cleanup_recording,
    list_input_devices,
    play_audio,
)
from prithi_model_router import NORMAL_MODE, PrithiModelRouter
from prithi_stt import MODEL_NAME as STT_MODEL_NAME
from prithi_stt import SUPPORTED_LANGUAGES, transcribe_audio
from prithi_voice import generate_voice
from prithi_transcript_quality import assess_transcript, RETRY_MESSAGE


APP_DIR = Path(__file__).resolve().parent
DEFAULT_STT_ENV = "PRITHI_DEFAULT_STT_LANGUAGE"
VOICE_REPLY_MODES = {"concise", "normal"}
CONCISE_VOICE_HINT = (
    "This response will be spoken aloud. Keep it to approximately 1–3 natural "
    "conversational sentences, avoid unnecessary repetition, and ask no more "
    "than one question unless the context genuinely requires more. Preserve the "
    "Prithi personality and the required structured JSON format. Use shorter "
    "spoken clauses, fewer formal constructions and unnecessary commas, and "
    "avoid repeated sympathy phrases and unnecessary explanations. Prefer one "
    "brief spoken sentence of roughly 10–25 words; use a second only when it adds "
    "real value, and a third only when genuinely necessary. Keep natural Bengali/Banglish. "
    "natural live-conversation phrasing. Avoid repeatedly asking variants of "
    "'What do you want to talk about?'"
)


def resolve_stt_language(requested: str | None) -> str:
    value = requested or os.environ.get(DEFAULT_STT_ENV, "auto")
    normalized = value.strip().lower()
    if normalized not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"{DEFAULT_STT_ENV} must be one of: {', '.join(sorted(SUPPORTED_LANGUAGES))}"
        )
    return normalized


def gpu_snapshot() -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        name, used, total = [part.strip() for part in completed.stdout.splitlines()[0].split(",")]
        return {
            "available": True,
            "name": name,
            "used_mib": int(used),
            "total_mib": int(total),
        }
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


class PrithiVoicePipeline:
    def __init__(
        self,
        brain: PrithiBrain,
        stt: Callable[..., dict[str, Any]] = transcribe_audio,
        voice: Callable[..., dict[str, Any]] = generate_voice,
        reply_mode: str | None = None,
        model_router: PrithiModelRouter | None = None,
    ) -> None:
        self.brain = brain
        self.stt = stt
        self.voice = voice
        self.model_router = model_router
        self.reply_mode = (reply_mode or os.environ.get("PRITHI_VOICE_REPLY_MODE", "normal")).strip().lower()
        if self.reply_mode not in VOICE_REPLY_MODES:
            raise ValueError(f"Unsupported voice reply mode: {self.reply_mode}")
        self.last_result: dict[str, Any] | None = None

    def reset(self) -> None:
        self.brain.reset_history()
        self.last_result = None

    def clear_conversation(self) -> None:
        self.brain.clear_conversation_history()
        self.last_result = None

    def reset_relationship(self) -> None:
        self.brain.reset_relationship()

    def transcribe_only(self, audio_path: str | Path, language: str) -> dict[str, Any]:
        result = self.stt(audio_path, language=language)
        previous_text = None
        history = getattr(self.brain, "history", ())
        try:
            prior_items = reversed(history)
        except TypeError:
            prior_items = iter(())
        for item in prior_items:
            if isinstance(item, dict) and item.get("role") == "user":
                previous_text = item.get("content")
                break
        result["quality_gate"] = assess_transcript(result, language, previous_text=previous_text)
        return result

    def respond_only(
        self,
        transcript: str,
        preferred_reply_language: str | None = None,
        memory_context: str | None = None,
        conversation_mode: str = NORMAL_MODE,
        age_confirmed: bool = False,
        adult_opt_in: bool = False,
        adaptive_context: str | None = None,
    ) -> dict[str, Any]:
        hints = [CONCISE_VOICE_HINT] if self.reply_mode == "concise" else []
        if adaptive_context:
            hints.append(adaptive_context)
        hint = "\n".join(hints) or None
        options = {}
        if hint:
            options["response_hint"] = hint
        if preferred_reply_language and preferred_reply_language != "auto":
            options["preferred_reply_language"] = preferred_reply_language
        if memory_context:
            options["memory_context"] = memory_context
        if self.model_router is not None:
            decision, routing = self.model_router.respond(
                self.brain,
                transcript,
                requested_mode=conversation_mode,
                age_confirmed=age_confirmed,
                adult_opt_in=adult_opt_in,
                **options,
            )
            routing_result = routing.as_dict()
        else:
            decision = self.brain.respond(transcript, **options)
            routing_result = {
                "conversation_mode": NORMAL_MODE,
                "selected_model": getattr(self.brain.backend, "model", None),
                "age_confirmed": False,
                "adult_opt_in": False,
                "switch_occurred": False,
                "switch_latency": 0.0,
                "deescalated": False,
                "disable_adult_mode": False,
                "safety_routed": False,
            }
        return {
            "reply": decision.reply,
            "language": decision.language,
            "emotion": decision.emotion,
            "voice_style": decision.voice_style.as_dict(),
            "generation_time": self.brain.last_generation_time,
            "preferred_reply_language": preferred_reply_language if preferred_reply_language != "auto" else None,
            "brain_returned_language": decision.language,
            "validated_reply_language": decision.language,
            "relationship_state": self.brain.relationship_state.as_dict(),
            "current_emotion": self.brain.current_emotion,
            "previous_emotion": self.brain.previous_emotion,
            "question_used": "?" in decision.reply or "？" in decision.reply,
            "routing": routing_result,
        }

    def synthesize_only(self, brain_result: dict[str, Any]) -> dict[str, Any]:
        return self.voice(
            brain_result["reply"],
            brain_result["language"],
            brain_result["emotion"],
            voice_style=brain_result.get("voice_style"),
        )

    def process_audio(
        self,
        audio_path: str | Path,
        language: str,
        memory_context: str | None = None,
        conversation_mode: str = NORMAL_MODE,
        age_confirmed: bool = False,
        adult_opt_in: bool = False,
        adaptive_context: str | None = None,
        adaptive_context_factory: Callable[[str], str] | None = None,
        adaptive_finalize: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        result: dict[str, Any] = {
            "input_path": str(Path(audio_path).expanduser()),
            "requested_stt_language": language,
            "status": "STARTED",
            "error": None,
        }
        try:
            result["stt"] = self.transcribe_only(audio_path, language)
        except Exception as exc:
            result.update(status="STT_FAILED", error=f"{type(exc).__name__}: {exc}")
            result["total_time"] = time.perf_counter() - started
            self.last_result = result
            return result

        transcript = str(result["stt"].get("text", "")).strip()
        result["transcript"] = transcript
        if not transcript or not result["stt"]["quality_gate"]["passed"]:
            result.update(status="STT_EMPTY", error=RETRY_MESSAGE)
            result["total_time"] = time.perf_counter() - started
            self.last_result = result
            return result

        try:
            if adaptive_context_factory is not None:
                adaptive_context = adaptive_context_factory(transcript)
            result["brain"] = self.respond_only(
                transcript,
                language if language != "auto" else None,
                memory_context=memory_context,
                conversation_mode=conversation_mode,
                age_confirmed=age_confirmed,
                adult_opt_in=adult_opt_in,
                adaptive_context=adaptive_context,
            )
            if adaptive_finalize is not None:
                adaptive_finalize(result["brain"])
        except Exception as exc:
            result.update(status="BRAIN_FAILED", error=f"{type(exc).__name__}: {exc}")
            result["total_time"] = time.perf_counter() - started
            self.last_result = result
            return result

        try:
            result["voice"] = self.synthesize_only(result["brain"])
            result["status"] = "SUCCESS"
        except Exception as exc:
            result.update(status="TTS_FAILED", error=f"{type(exc).__name__}: {exc}")
        result["total_time"] = time.perf_counter() - started
        result["gpu"] = gpu_snapshot()
        self.last_result = result
        return result


def print_result(result: dict[str, Any]) -> None:
    print(f"\nUSER AUDIO: {result['input_path']}")
    print(f"TRANSCRIPT: {result.get('transcript', 'unavailable')}")
    if stt := result.get("stt"):
        print("STT:")
        print(f"  detected language: {stt['detected_language']}")
        print(f"  language probability: {float(stt['language_probability']):.4f}")
        print(f"  model load time: {float(stt.get('model_load_time', 0.0)):.3f} seconds")
        print(f"  warm model reused: {bool(stt.get('model_reused', False))}")
        print(f"  transcription time: {float(stt['transcription_time']):.3f} seconds")
        print(f"  device/compute type: {stt.get('device', 'unknown')}/{stt.get('compute_type', 'unknown')}")
    if brain := result.get("brain"):
        print(f"PRITHI: {brain['reply']}")
        print("BRAIN:")
        print(f"  language: {brain['language']}")
        print(f"  emotion: {brain['emotion']}")
        print(f"  voice style: {json.dumps(brain['voice_style'], ensure_ascii=False, sort_keys=True)}")
        print(f"  LLM generation time: {float(brain['generation_time']):.3f} seconds")
    if voice := result.get("voice"):
        print("VOICE:")
        print(f"  engine: {voice['tts_engine']}")
        print(f"  voice/model: {voice['model_voice']}")
        print(f"  locale: {voice['locale']}")
        print(f"  TTS generation time: {float(voice['generation_time']):.3f} seconds")
        print(f"  output WAV path: {voice['output_path']}")
        print(f"  output duration: {float(voice['duration']):.3f} seconds")
        print(f"  fallback status: {voice['fallback_occurred']}")
    print("TOTAL:")
    print(f"  total processing time: {float(result['total_time']):.3f} seconds")
    print(f"  status: {result['status']}")
    if gpu := result.get("gpu"):
        if gpu.get("available"):
            print(
                f"  GPU: {gpu['name']}, {gpu['used_mib']} MiB used / "
                f"{gpu['total_mib']} MiB total"
            )
        else:
            print(f"  GPU metrics unavailable: {gpu.get('error', 'unknown error')}")
    if result.get("error"):
        print(f"  error: {result['error']}")


def print_debug(pipeline: PrithiVoicePipeline, backend: OpenAICompatibleBackend, default_language: str) -> None:
    last = pipeline.last_result or {}
    brain = last.get("brain", {})
    voice = last.get("voice", {})
    print(f"Current Ollama model: {backend.model}")
    print(f"STT model: {STT_MODEL_NAME}")
    print(f"STT default language: {default_language}")
    print(f"Conversation history count: {pipeline.brain.history_turn_count}")
    behavior = pipeline.brain.debug_state()
    print(f"Current emotion: {behavior['current_emotion']}")
    print(f"Previous emotion: {behavior['previous_emotion']}")
    print(f"Familiarity: {behavior['familiarity']:.3f}")
    print(f"Trust: {behavior['trust']:.3f}")
    print(f"Affection: {behavior['affection']:.3f}")
    print(f"Playfulness: {behavior['playfulness']:.3f}")
    print(f"Romantic tension: {behavior['romantic_tension']:.3f}")
    print(f"Last transcript: {last.get('transcript', 'none') or 'none'}")
    print(f"Last emotion: {brain.get('emotion', 'none')}")
    print(f"Last response audio path: {voice.get('output_path', 'none')}")


def build_pipeline() -> tuple[PrithiVoicePipeline, OpenAICompatibleBackend]:
    try:
        router = PrithiModelRouter.from_environment()
        router.verify_models_available()
        backend = router.normal_backend
    except Exception as exc:
        raise RuntimeError(f"LLM configuration/connectivity failed: {type(exc).__name__}: {exc}") from exc
    return PrithiVoicePipeline(PrithiBrain(backend, history_turns=8), model_router=router), backend


def run_mic_mode(
    pipeline: PrithiVoicePipeline,
    selected_language: str,
    sample_rate: int,
    input_device: int | str | None,
) -> int:
    print("Prithi Voice Chat")
    print("Press Enter to start recording. Speak, then press Enter again to stop.")
    print("Commands: /debug is available in file mode; /reset, /quit, /exit are available here.")
    recorder = PushToTalkRecorder(
        RecordingConfig(sample_rate=sample_rate, device=input_device)
    )
    while True:
        try:
            command = input("Ready: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            recorder.cancel()
            print("\nVoice chat ended.")
            return 0
        if command in {"/quit", "/exit"}:
            print("Voice chat ended.")
            return 0
        if command == "/reset":
            pipeline.reset()
            print("In-memory conversation history cleared.")
            continue
        if command:
            print("Press Enter without text to start recording, or use /reset, /quit, /exit.")
            continue

        recording_path: Path | None = None
        try:
            recorder.start()
            input("Recording... press Enter to stop: ")
            recording_path = recorder.stop()
            print(f"Recording duration: {recorder.last_duration:.3f} seconds")
            result = pipeline.process_audio(recording_path, selected_language)
            print_result(result)
            if result.get("voice"):
                try:
                    play_audio(result["voice"]["output_path"])
                    print("Playback: complete")
                except PlaybackUnavailableError as exc:
                    print(f"Playback unavailable on remote server. WAV: {result['voice']['output_path']}")
                    print(f"Playback detail: {exc}")
        except KeyboardInterrupt:
            recorder.cancel()
            print("\nRecording cancelled.")
        except Exception as exc:
            recorder.cancel()
            print(f"Microphone turn error: {type(exc).__name__}: {exc}")
        finally:
            cleanup_recording(recording_path)


def main() -> int:
    load_local_env()
    parser = argparse.ArgumentParser(description="Prithi audio-file to audio-response pipeline")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--audio", help="Path to one input audio file")
    mode.add_argument("--interactive", action="store_true", help="Repeatedly accept audio file paths")
    mode.add_argument("--mic", action="store_true", help="Manual push-to-talk microphone mode")
    parser.add_argument("--language", choices=sorted(SUPPORTED_LANGUAGES), default=None)
    parser.add_argument("--sample-rate", type=int, choices=(16000, 24000), default=16000)
    parser.add_argument("--input-device", default=None, help="Input device index or name")
    args = parser.parse_args()
    try:
        selected_language = resolve_stt_language(args.language)
        if args.mic:
            devices = list_input_devices()
            if not devices:
                print("Microphone devices visible to Lightning: none")
                print("Direct microphone mode is not possible in this remote Studio.")
                print("Local browser microphone required.")
                return 4
        pipeline, backend = build_pipeline()
    except Exception as exc:
        print(f"Startup error: {type(exc).__name__}: {exc}")
        print("No STT, LLM generation, or TTS request was made.")
        return 2

    if args.audio:
        result = pipeline.process_audio(args.audio, selected_language)
        print_result(result)
        return 0 if result["status"] == "SUCCESS" else 1

    if args.mic:
        device: int | str | None = args.input_device
        if isinstance(device, str) and device.isdigit():
            device = int(device)
        print("Microphone input devices:")
        for item in devices:
            print(f"  {item['index']}: {item['name']} ({item['max_input_channels']} input channels)")
        return run_mic_mode(pipeline, selected_language, args.sample_rate, device)

    print("Prithi Voice Chat")
    print("Enter an audio file path or type /quit.")
    while True:
        try:
            entry = input("Audio: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nVoice chat ended.")
            return 0
        command = entry.lower()
        if command in {"/quit", "/exit"}:
            print("Voice chat ended.")
            return 0
        if command == "/reset":
            pipeline.reset()
            print("In-memory conversation history cleared.")
            continue
        if command == "/debug":
            print_debug(pipeline, backend, selected_language)
            continue
        if not entry:
            continue
        print_result(pipeline.process_audio(entry, selected_language))


if __name__ == "__main__":
    raise SystemExit(main())
