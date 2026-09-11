#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import time

import httpx

from prithi_brain import PrithiBrain
from prithi_chat import load_local_env
from prithi_model_router import ADULT_MODE, NORMAL_MODE, PrithiModelRouter


def gpu_memory() -> dict[str, object]:
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"],
            text=True,
            timeout=10,
        ).strip().splitlines()[0]
        name, used, total = [item.strip() for item in output.split(",")]
        return {"name": name, "used_mib": int(used), "total_mib": int(total)}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def ollama_loaded() -> list[dict[str, object]]:
    try:
        response = httpx.get("http://127.0.0.1:11434/api/ps", timeout=10)
        response.raise_for_status()
        return [
            {"name": item.get("name"), "size_vram": item.get("size_vram")}
            for item in response.json().get("models", [])
        ]
    except Exception as exc:
        return [{"error": f"{type(exc).__name__}: {exc}"}]


def run_turn(brain: PrithiBrain, router: PrithiModelRouter, text: str, mode: str, enabled: bool) -> dict[str, object]:
    started = time.perf_counter()
    reply, routing = router.respond(
        brain,
        text,
        requested_mode=mode,
        age_confirmed=enabled,
        adult_opt_in=enabled,
        preferred_reply_language="bengali",
    )
    return {
        "conversation_mode": routing.conversation_mode,
        "model": routing.selected_model,
        "switch_occurred": routing.switch_occurred,
        "switch_latency": round(routing.switch_latency, 3),
        "total_latency": round(time.perf_counter() - started, 3),
        "language": reply.language,
        "emotion": reply.emotion,
        "reply": reply.reply,
        "ollama_loaded": ollama_loaded(),
        "gpu": gpu_memory(),
    }


def main() -> int:
    load_local_env()
    router = PrithiModelRouter.from_environment()
    router.verify_models_available()
    brain = PrithiBrain(router.normal_backend, history_turns=8)
    results = [
        run_turn(brain, router, "আজ তোমার সাথে একটু শান্তভাবে গল্প করতে চাই।", NORMAL_MODE, False),
        run_turn(brain, router, "আমরা দুজন প্রাপ্তবয়স্ক এবং সম্মত। আজ একটু বেশি কাছের, sensual কিন্তু কোমল কথা বলতে চাই।", ADULT_MODE, True),
        run_turn(brain, router, "Stop, এখন normal কথা বলি। আজকের দিনটা নিয়ে গল্প করি।", ADULT_MODE, True),
    ]
    print(json.dumps({"turns": results, "history_turns": brain.history_turn_count}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
