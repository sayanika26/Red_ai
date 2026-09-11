import secrets
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from llm_provider import OpenAICompatibleBackend
from prithi_brain import PrithiBrain
from prithi_chat import load_local_env
from prithi_memory import MemoryStore, stable_user_id


def main() -> None:
    load_local_env()
    store = MemoryStore()
    user_id = stable_user_id(secrets.token_urlsafe(32))
    try:
        store.update_profile(user_id, preferred_language="bengali")
        store.add_memory(user_id, "preference", "Prefers tea over coffee.", .8)
        prompt = store.build_prompt(user_id, "আজকে coffee খাবো ভাবছি।")
        brain = PrithiBrain(OpenAICompatibleBackend.from_environment(), history_turns=8)
        reply = brain.respond(
            "আজকে coffee খাবো ভাবছি।",
            preferred_reply_language="bengali",
            memory_context=prompt,
        )
        print(f"Reply: {reply.reply}")
        print(f"Language: {reply.language}")
        print(f"Emotion: {reply.emotion}")
        print(f"Remembered preference supplied: {'Prefers tea over coffee.' in prompt}")
    finally:
        store.delete_user_memory(user_id)
        print("Isolated callback test memory removed: yes")


if __name__ == "__main__":
    main()
