import json
import os
from pathlib import Path

from llm_provider import LLMConfigurationError, OpenAICompatibleBackend
from prithi_brain import PrithiBrain


APP_DIR = Path(__file__).resolve().parent
ENV_NAMES = {"PRITHI_LLM_BASE_URL", "PRITHI_LLM_API_KEY", "PRITHI_LLM_MODEL"}


def load_local_env(path: Path = APP_DIR / ".env") -> bool:
    """Load the three supported settings without overwriting shell variables."""
    if not path.is_file():
        return False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if name not in ENV_NAMES:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(name, value)
    return True


def print_preflight_configuration(env_loaded: bool) -> None:
    print(f"Local app/.env loaded: {env_loaded}")
    print(f"Base URL configured: {bool(os.environ.get('PRITHI_LLM_BASE_URL', '').strip())}")
    print(f"Model configured: {bool(os.environ.get('PRITHI_LLM_MODEL', '').strip())}")
    print(f"API key exists: {bool(os.environ.get('PRITHI_LLM_API_KEY', '').strip())}")


def main() -> int:
    env_loaded = load_local_env()
    print_preflight_configuration(env_loaded)
    try:
        backend = OpenAICompatibleBackend.from_environment()
    except LLMConfigurationError as exc:
        print(f"Configuration error: {exc}")
        print("Provider preflight was not run. TTS was not called.")
        return 2

    brain = PrithiBrain(backend, history_turns=8)
    try:
        backend.verify_model_available()
        preflight_time = brain.preflight()
    except Exception as exc:
        print(f"Provider connectivity error: {type(exc).__name__}: {exc}")
        print("TTS was not called.")
        return 3
    print(f"Provider connectivity: OK ({preflight_time:.3f} seconds)")
    print(f"Provider: {backend.provider}")
    print("Prithi text chat is ready. Commands: /debug, /reset, /quit, /exit")

    last_language = None
    last_emotion = None
    last_style = None
    last_audio_path = None

    while True:
        try:
            user_text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nChat ended.")
            return 0
        command = user_text.lower()
        if command in {"/quit", "/exit"}:
            print("Chat ended.")
            return 0
        if command == "/reset":
            brain.reset_history()
            print("In-memory conversation history cleared.")
            continue
        if command == "/debug":
            print(f"Provider: {backend.provider}")
            print(f"Current model: {backend.model}")
            print(f"History turn count: {brain.history_turn_count}")
            print(f"Last selected language: {last_language or 'none'}")
            print(f"Last emotion: {last_emotion or 'none'}")
            print(f"Last voice style: {json.dumps(last_style, sort_keys=True) if last_style else 'none'}")
            print(f"Last audio path: {last_audio_path or 'none'}")
            continue
        if not user_text:
            continue

        print(f"User text: {user_text}")
        print(f"Model used: {backend.model}")
        try:
            decision = brain.respond(user_text)
        except Exception as exc:
            print(f"Brain error: {type(exc).__name__}: {exc}")
            print("TTS was not called for this message.")
            continue

        last_language = decision.language
        last_emotion = decision.emotion
        last_style = decision.voice_style.as_dict()
        print(f"Prithi: {decision.reply}")
        print(f"Reply language: {last_language}")
        print(f"Selected emotion: {last_emotion}")
        print(f"Voice style: {json.dumps(last_style, sort_keys=True)}")
        print(f"LLM generation time: {brain.last_generation_time:.3f} seconds")
        try:
            from prithi_voice import generate_voice

            voice_result = generate_voice(decision.reply, decision.language, decision.emotion)
            last_audio_path = str(voice_result["output_path"])
            print(f"TTS generation time: {float(voice_result['generation_time']):.3f} seconds")
            print(f"Audio output path: {last_audio_path}")
        except Exception as exc:
            print(f"TTS error: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
