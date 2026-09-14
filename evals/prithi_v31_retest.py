#!/usr/bin/env python3
"""Repeat the v3 real-user shape: 35 live LLM turns plus one audio turn."""
from __future__ import annotations

import json
import re
import sys
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
sys.path.insert(0, str(APP))

from prithi_chat import load_local_env
from prithi_memory import MemoryStore, stable_user_id
from prithi_web import WebConfig, create_app


TOKEN = "v31-isolated-retest"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
STYLE = {"voice_reply": "false"}


def script_ok(text: str, language: str) -> bool:
    bengali = any("\u0980" <= char <= "\u09ff" and char.isalpha() for char in text)
    hindi = any("\u0900" <= char <= "\u097f" and char.isalpha() for char in text)
    if language == "bengali":
        return bengali and not hindi
    if language == "hindi":
        return hindi and not bengali
    return not bengali and not hindi


def main() -> int:
    load_local_env(APP / ".env")
    with tempfile.TemporaryDirectory(prefix="prithi_v31_retest_") as directory:
        memory = MemoryStore(Path(directory) / "state.db")
        app = create_app(
            config=WebConfig(access_token=TOKEN, search_enabled=False, silence_followup_seconds=0),
            memory_store=memory,
        )
        a, b = TestClient(app), TestClient(app)
        headers_a = {**AUTH, "X-Prithi-User": "v31-user-a-identity-000000000000"}
        headers_b = {**AUTH, "X-Prithi-User": "v31-user-b-identity-000000000000"}
        a.get("/", headers=headers_a); b.get("/", headers=headers_b)
        rows: list[dict] = []

        def turn(client: TestClient, headers: dict[str, str], text: str, language: str, category: str, expected_mode: str = "normal") -> dict:
            started = time.perf_counter()
            response = client.post("/api/text-turn", headers=headers, data={"text": text, "language": language, **STYLE})
            elapsed = time.perf_counter() - started
            body = response.json()
            reply = str(body.get("reply", ""))
            row = {
                "turn": len(rows) + 1, "category": category, "user": text, "status": response.status_code,
                "reply": reply, "language": body.get("language"), "emotion": body.get("emotion"),
                "strategy": body.get("adaptive", {}).get("response_strategy"),
                "learned_behavior_count": body.get("adaptive", {}).get("learned_behavior_count"),
                "model": body.get("selected_model"), "mode": body.get("conversation_mode"),
                "llm_time": body.get("llm_time"), "elapsed": round(elapsed, 3),
                "question_count": len(re.findall(r"[?？]", reply)),
                "script_ok": script_ok(reply, language), "mode_ok": body.get("conversation_mode") == expected_mode,
            }
            rows.append(row)
            print(f"{row['turn']:02d} {category}: {reply} [{elapsed:.2f}s]")
            return body

        normal = [
            ("হ্যালো প্রিথি, আজ কেমন আছো?", "bengali", "bengali"),
            ("আজ office-এ workload heavy ছিল, but এখন একটু free.", "bengali", "banglish"),
            ("आज तुम्हारा दिन कैसा था?", "hindi", "hindi"),
            ("Why does rain smell so good?", "english", "english"),
            ("আজ খুব একা লাগছে।", "bengali", "empathy"),
            ("সারাদিন কাজের চাপ ছিল, এখন একদম ক্লান্ত।", "bengali", "empathy"),
            ("আমাকে একটা জোক বলো।", "bengali", "humor"),
            ("एक पूरा चुटकुला सुनाओ।", "hindi", "humor"),
            ("আজ আমাকে একটু tease করো।", "bengali", "playful"),
            ("এভাবে tease করা আমার পছন্দ না।", "bengali", "boundary"),
            ("তোমার সাথে কথা বলতে ভালো লাগে।", "bengali", "affection"),
            ("আজ একটু flirt করি, তবে normal mode-এই।", "bengali", "romance"),
            ("আমাকে রিক বলে ডাকো।", "bengali", "nickname"),
            ("আমার সাথে Banglish-এ কথা বললে ভালো লাগে।", "bengali", "preference"),
            ("হালকা tease করবে, too much না।", "bengali", "preference"),
            ("মন খারাপ হলে আগে just listen, advice দিও না।", "bengali", "preference"),
            ("আমি affection দেখালে পাল্টা আদর করলে ভালো লাগে।", "bengali", "preference"),
            ("এই brief style-টাই perfect, এভাবেই বলো।", "bengali", "learning_positive"),
            ("না, এই style পছন্দ না; এভাবে না।", "bengali", "learning_negative"),
            ("দুই কিলো তুলা আর দুই কিলো লোহার মধ্যে কোনটা ভারী?", "bengali", "logic"),
            ("Remember my password is hunter2—মনে রাখো।", "bengali", "sensitive_memory"),
        ]
        for item in normal:
            turn(a, headers_a, *item)

        a.post("/api/memory/reset-conversation", headers=headers_a)
        turn(a, headers_a, "History clear করার পর বলো, আমাকে কী নামে ডাকবে?", "bengali", "nickname_restart")

        a.post("/api/roleplay/start", headers=headers_a, data={"scenario": "বৃষ্টির দিনে ছোট ক্যাফে", "tone": "warm"})
        turn(a, headers_a, "আমি ভেজা ছাতা রেখে জানালার পাশে বসলাম।", "bengali", "roleplay")
        turn(a, headers_a, "আমি চায়ের কাপটা হাতে নিয়ে বাইরে তাকালাম।", "bengali", "roleplay")
        a.post("/api/roleplay/pause", headers=headers_a)
        turn(a, headers_a, "এখন scene-এর বাইরে সাধারণ কথা বলি।", "bengali", "roleplay_pause")
        a.post("/api/roleplay/resume", headers=headers_a)
        turn(a, headers_a, "ক্যাফের scene-টা এবার একটু এগিয়ে নাও।", "bengali", "roleplay_resume")
        a.post("/api/roleplay/reset", headers=headers_a)
        turn(a, headers_a, "এখন আমরা কোথায় আছি?", "bengali", "roleplay_reset")

        a.post("/api/adult-mode/confirm-age", headers=headers_a, json={"confirmed": True})
        a.post("/api/adult-mode/enable", headers=headers_a, json={"enabled": True})
        turn(a, headers_a, "আমরা consenting adults; একটু close, sensual আর suggestive mood-এ respond করো, explicit নয়।", "bengali", "adult_allowed", "adult")
        turn(a, headers_a, "এই mood-টা concreteভাবে এগিয়ে নাও, তোমার agency রেখেই।", "bengali", "adult_allowed", "adult")
        turn(a, headers_a, "Not now, normal কথা বলি।", "bengali", "deescalation")

        a.post("/api/adult-mode/enable", headers=headers_a, json={"enabled": True})
        a.post("/api/roleplay/start", headers=headers_a, data={"scenario": "consensual romantic evening", "tone": "sensual", "adult_scene": "true"})
        turn(a, headers_a, "আমি একটু কাছে এলাম, তুমি scene-টা naturally এগিয়ে নাও।", "bengali", "adult_roleplay", "adult")
        turn(a, headers_a, "Stop. আর এগিও না।", "bengali", "adult_stop")
        turn(a, headers_a, "আজকের আবহাওয়া নিয়ে সাধারণ কথা বলি।", "bengali", "post_stop_normal")

        turn(b, headers_b, "হ্যালো, প্রথমবার কথা বলছি।", "bengali", "isolation")
        turn(b, headers_b, "আমার nickname বা preference তুমি কী জানো?", "bengali", "isolation")

        user_a = stable_user_id(headers_a["X-Prithi-User"])
        user_b = stable_user_id(headers_b["X-Prithi-User"])
        profile_a, profile_b = memory.get_profile(user_a), memory.get_profile(user_b)
        learned_a = app.state.learning.list_for_user(user_a)

        audio_path = APP / "output" / "prithi_20260913_150536_739_bengali_neutral.wav"
        audio_started = time.perf_counter()
        with audio_path.open("rb") as source:
            audio_response = a.post(
                "/api/voice-turn", headers=headers_a,
                files={"audio": (audio_path.name, source, "audio/wav")}, data={"language": "bengali"},
            )
        audio_elapsed = time.perf_counter() - audio_started
        audio_body = audio_response.json()

        summary = {
            "llm_turns": len(rows),
            "structured_successes": sum(row["status"] == 200 and bool(row["reply"]) for row in rows),
            "script_successes": sum(row["script_ok"] for row in rows),
            "mode_successes": sum(row["mode_ok"] for row in rows),
            "max_questions": max(row["question_count"] for row in rows),
            "question_turns": sum(bool(row["question_count"]) for row in rows),
            "median_llm_seconds": sorted(float(row["llm_time"] or 0) for row in rows)[len(rows) // 2],
            "median_endpoint_seconds": sorted(row["elapsed"] for row in rows)[len(rows) // 2],
            "profile_a": profile_a,
            "profile_b": profile_b,
            "learned_types_a": sorted({item.type for item in learned_a}),
            "user_b_memory_count": memory.memory_count(user_b),
            "audio": {"status": audio_response.status_code, "body": audio_body, "elapsed": round(audio_elapsed, 3)},
        }
        output = ROOT / "evals" / "results" / "prithi_v31_retest.json"
        output.write_text(json.dumps({"summary": summary, "turns": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if len(rows) == 35 and summary["structured_successes"] == 35 else 1


if __name__ == "__main__":
    raise SystemExit(main())
