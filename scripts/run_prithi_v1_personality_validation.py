#!/usr/bin/env python3
"""Run the final five-turn Prithi v1 personality validation without TTS."""

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from llm_provider import OpenAICompatibleBackend
from prithi_brain import PrithiBrain
from prithi_chat import load_local_env


TURNS = [
    ("neutral", "হ্যালো পৃথি, আজ কাজ মোটামুটি ছিল।"),
    ("caring", "তবে বিকেলে চাপ বেড়ে গিয়েছিল, এখন একটু ক্লান্ত লাগছে।"),
    ("playful", "আচ্ছা, এত সিরিয়াস না হয়ে আমাকে একটু tease করো তো।"),
    ("affectionate", "তোমার সাথে কথা বললে সত্যিই মনটা হালকা হয়ে যায়।"),
    ("flirtatious", "আজকে তোমার সাথে একটু মিষ্টি আর flirty ভাবে কথা বলতে ইচ্ছে করছে।"),
]


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def main() -> None:
    load_local_env()
    brain = PrithiBrain(OpenAICompatibleBackend.from_environment(), history_turns=8)
    rows: list[dict[str, object]] = []
    for turn, (intention, user_text) in enumerate(TURNS, 1):
        reply = brain.respond(user_text, preferred_reply_language="bengali")
        row = {
            "turn": turn,
            "intention": intention,
            "user": user_text,
            "reply": reply.reply,
            "language": reply.language,
            "emotion": reply.emotion,
            "question": "?" in reply.reply or "？" in reply.reply,
            "llm_time": brain.last_generation_time,
            "relationship": brain.relationship_state.as_dict(),
        }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    replies = [normalized(str(row["reply"])) for row in rows]
    duplicate_replies = len(replies) != len(set(replies))
    counselor_phrase = any("বুঝতেই পারছি" in str(row["reply"]) for row in rows)
    questions = sum(bool(row["question"]) for row in rows)
    languages_ok = all(row["language"] == "bengali" for row in rows)
    emotion_path = [str(row["emotion"]) for row in rows]
    emotion_ok = (
        emotion_path[0] in {"neutral", "warm"}
        and emotion_path[1] in {"caring", "warm", "intimate"}
        and emotion_path[2] in {"playful", "warm", "flirtatious"}
        and emotion_path[3] in {"affectionate", "warm", "intimate", "caring"}
        and emotion_path[4] in {"flirtatious", "attraction", "playful", "affectionate"}
    )
    summary = {
        "turns": len(rows),
        "languages_ok": languages_ok,
        "emotion_path": emotion_path,
        "emotion_path_reasonable": emotion_ok,
        "duplicate_replies": duplicate_replies,
        "repeated_counselor_phrase": counselor_phrase,
        "question_count": questions,
        "question_frequency_reasonable": questions <= 3,
        "history_turn_count": brain.history_turn_count,
    }
    output = ROOT / "runtime" / "validation" / "prithi_v1_personality_results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"turns": rows, "summary": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if not all(
        (
            languages_ok,
            emotion_ok,
            not duplicate_replies,
            not counselor_phrase,
            questions <= 3,
            brain.history_turn_count == 5,
        )
    ):
        raise SystemExit("PERSONALITY_VALIDATION=FAILED")
    print("PERSONALITY_VALIDATION=PASS")


if __name__ == "__main__":
    main()
