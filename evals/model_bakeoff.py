#!/usr/bin/env python3
"""Deterministic, local-only Stage 20 model bake-off for Prithi."""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
sys.path.insert(0, str(APP))

from prithi_brain import BrainOutputError, PrithiBrain, SYSTEM_PROMPT
from prithi_chat import load_local_env


REFUSAL_PATTERNS = (
    "i can't", "i cannot", "can't help", "cannot help", "not able to", "as an ai",
    "আমি পারি না", "আমি সাহায্য করতে পারি না", "এটা করতে পারব না",
    "मैं नहीं कर सकती", "मैं मदद नहीं कर सकती", "ऐसा नहीं कर सकती",
)
ROBOTIC_PATTERNS = ("as an ai", "language model", "virtual assistant", "আমি একটি ai", "আমি এআই")
COUNSELOR_PATTERNS = ("বুঝতেই পারছি", "how does that make you feel", "आप कैसा महसूस")
FALSE_REAL_WORLD_PATTERNS = (
    r"\bi went to\b", r"\bi ate\b", r"\bi watched\b", r"আমি আজ অফিসে", r"আমি খেয়েছি", r"আমি দেখেছি",
    r"मैं आज ऑफिस", r"मैंने खाया", r"मैंने देखा",
)


class OllamaMetricsBackend:
    def __init__(self, model: str, base_url: str, temperature: float, max_tokens: int) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.calls: list[dict[str, Any]] = []

    def complete(self, messages: list[dict[str, str]]) -> str:
        started = time.perf_counter()
        first_token: float | None = None
        pieces: list[str] = []
        final: dict[str, Any] = {}
        body = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "format": "json",
            "think": False,
            "keep_alive": "20m",
            "options": {"temperature": self.temperature, "num_predict": self.max_tokens},
        }
        with httpx.stream("POST", f"{self.base_url}/api/chat", json=body, timeout=300.0) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                content = chunk.get("message", {}).get("content", "")
                if content:
                    if first_token is None:
                        first_token = time.perf_counter() - started
                    pieces.append(content)
                if chunk.get("done"):
                    final = chunk
        elapsed = time.perf_counter() - started
        eval_count = int(final.get("eval_count") or 0)
        eval_duration = int(final.get("eval_duration") or 0) / 1e9
        self.calls.append({
            "latency": elapsed,
            "first_token_latency": first_token,
            "prompt_tokens": int(final.get("prompt_eval_count") or 0),
            "generation_tokens": eval_count,
            "tokens_per_second": eval_count / eval_duration if eval_count and eval_duration else 0.0,
            "load_duration": int(final.get("load_duration") or 0) / 1e9,
            "total_duration": int(final.get("total_duration") or 0) / 1e9,
            "raw": "".join(pieces),
        })
        return "".join(pieces)


def script_counts(text: str) -> dict[str, int]:
    return {
        "bengali": sum("\u0980" <= char <= "\u09ff" for char in text),
        "devanagari": sum("\u0900" <= char <= "\u097f" for char in text),
        "latin": sum(char.isascii() and char.isalpha() for char in text),
        "unsupported": sum(
            char.isalpha()
            and not ("\u0980" <= char <= "\u09ff")
            and not ("\u0900" <= char <= "\u097f")
            and "LATIN" not in unicodedata.name(char, "")
            for char in text
        ),
    }


def language_score(text: str, language: str, banglish: bool = False) -> float:
    counts = script_counts(text)
    total = sum(counts.values()) or 1
    if language == "bengali":
        if counts["devanagari"] > counts["bengali"] or not counts["bengali"]:
            return 1.0
        score = 5.0 if counts["bengali"] / total >= 0.55 else 4.0
        if banglish and not counts["latin"]:
            score -= 0.5
    elif language == "hindi":
        score = 5.0 if counts["devanagari"] / total >= 0.65 else (3.0 if counts["devanagari"] else 1.0)
    else:
        score = 5.0 if counts["latin"] / total >= 0.8 else (3.0 if counts["latin"] else 1.0)
    if counts["unsupported"]:
        score -= min(2.0, counts["unsupported"] / 3)
    return round(max(1.0, score), 2)


def emotion_score(actual: str, expected: list[str]) -> float:
    if actual in expected:
        return 5.0
    adjacent = {
        "neutral": {"warm"}, "warm": {"neutral", "caring", "affectionate", "playful"},
        "caring": {"warm", "intimate"}, "playful": {"warm", "flirtatious"},
        "affectionate": {"warm", "intimate", "flirtatious"},
        "flirtatious": {"playful", "affectionate", "attraction", "pleasure"},
        "intimate": {"caring", "affectionate", "attraction", "pleasure"},
        "attraction": {"flirtatious", "intimate", "pleasure", "aroused"},
        "pleasure": {"flirtatious", "intimate", "attraction"},
        "aroused": {"attraction", "pleasure", "intimate"},
    }
    return 4.0 if any(actual in adjacent.get(item, set()) for item in expected) else 2.0


def looks_refusal(text: str) -> bool:
    folded = text.casefold()
    return any(marker in folded for marker in REFUSAL_PATTERNS)


def score_result(case: dict[str, Any], result: dict[str, Any]) -> dict[str, float | None]:
    if not result.get("success"):
        return {name: 1.0 for name in (
            "bengali_naturalness", "banglish_naturalness", "hindi_quality", "english_quality",
            "empathy", "emotional_warmth", "personality_adherence", "playful_flirty_naturalness",
            "adult_sensual_capability", "consent_boundary_following", "hallucination_tendency",
            "repetition", "relationship_continuity", "json_schema_compliance",
        )} | {"unnecessary_refusal": 5.0}
    reply = result["reply"]
    text = reply["reply"]
    tags = set(case["tags"])
    refusal = looks_refusal(text)
    expected_score = emotion_score(reply["emotion"], case["expected_emotions"])
    word_count = len(text.split())
    personality = 5.0
    folded = text.casefold()
    if any(marker in folded for marker in ROBOTIC_PATTERNS):
        personality -= 2.0
    if any(marker in folded for marker in COUNSELOR_PATTERNS):
        personality -= 1.0
    if word_count > 70 or word_count < 2:
        personality -= 1.0
    hallucination = 1.0 if any(re.search(pattern, folded) for pattern in FALSE_REAL_WORLD_PATTERNS) else 5.0
    consent = 5.0
    if "consent" in tags or "stop" in tags:
        consent = 5.0 if reply["emotion"] in {"neutral", "warm", "caring"} and not refusal else 2.0
    adult = None
    if "sensual" in tags:
        adult = 1.0 if refusal else expected_score
    flirty = None
    if "flirty" in tags or "playful" in tags:
        flirty = 1.0 if refusal else expected_score
    empathy = expected_score if "empathy" in tags or "loneliness" in tags else None
    warmth = round(min(5.0, 1.0 + 4.0 * float(reply["voice_style"].get("warmth", 0.0))), 2)
    return {
        "bengali_naturalness": language_score(text, "bengali") if case["language"] == "bengali" and "banglish" not in tags else None,
        "banglish_naturalness": language_score(text, "bengali", True) if "banglish" in tags else None,
        "hindi_quality": language_score(text, "hindi") if case["language"] == "hindi" else None,
        "english_quality": language_score(text, "english") if case["language"] == "english" else None,
        "empathy": empathy,
        "emotional_warmth": warmth,
        "personality_adherence": round(max(1.0, personality), 2),
        "playful_flirty_naturalness": flirty,
        "adult_sensual_capability": adult,
        "consent_boundary_following": consent if "consent" in tags or "stop" in tags else None,
        "unnecessary_refusal": 1.0 if refusal else 5.0,
        "hallucination_tendency": hallucination,
        "repetition": 5.0,
        "relationship_continuity": None,
        "json_schema_compliance": 5.0 if result["attempts"] == 1 else 3.0,
    }


def run_case(model: str, backend: OllamaMetricsBackend, case: dict[str, Any], dataset: dict[str, Any], brain: PrithiBrain | None = None) -> dict[str, Any]:
    brain = brain or PrithiBrain(backend, history_turns=int(dataset["generation"]["history_turns"]), adult_mode=bool(case.get("adult_mode")))
    before = len(backend.calls)
    hint = dataset["adult_context"] if case.get("adult_mode") else None
    started = time.perf_counter()
    try:
        answer = brain.respond(
            case["user"], response_hint=hint, preferred_reply_language=case["language"]
        )
        success = True
        error = ""
        reply = {"reply": answer.reply, "language": answer.language, "emotion": answer.emotion, "voice_style": answer.voice_style.as_dict()}
    except Exception as exc:
        success = False
        error = f"{type(exc).__name__}: {exc}"
        reply = None
    call_metrics = backend.calls[before:]
    return {
        "model": model,
        "case_id": case.get("id", f"continuity_{case.get('turn')}"),
        "category": case.get("category", "continuity"),
        "tags": case.get("tags", ["continuity"]),
        "user": case["user"],
        "expected_emotions": case["expected_emotions"],
        "success": success,
        "error": error,
        "reply": reply,
        "attempts": len(call_metrics),
        "retry_required": len(call_metrics) > 1,
        "latency": time.perf_counter() - started,
        "first_token_latency": call_metrics[0]["first_token_latency"] if call_metrics else None,
        "generation_tokens": sum(item["generation_tokens"] for item in call_metrics),
        "tokens_per_second": statistics.mean([item["tokens_per_second"] for item in call_metrics if item["tokens_per_second"]]) if any(item["tokens_per_second"] for item in call_metrics) else 0.0,
        "load_duration": call_metrics[0]["load_duration"] if call_metrics else None,
        "raw_attempts": [item["raw"] for item in call_metrics],
    }


def ollama_stop(binary: Path, models: list[str]) -> None:
    for model in models:
        subprocess.run([str(binary), "stop", model], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    time.sleep(1.0)


def model_runtime(base_url: str, model: str) -> dict[str, Any]:
    tags = httpx.get(f"{base_url}/api/tags", timeout=30).json().get("models", [])
    wanted = model.casefold()
    disk = next((int(item.get("size", 0)) for item in tags if str(item.get("name") or item.get("model") or "").casefold() == wanted), 0)
    running = httpx.get(f"{base_url}/api/ps", timeout=30).json().get("models", [])
    active = next((item for item in running if str(item.get("name") or item.get("model") or "").casefold() == wanted), {})
    return {"disk_bytes": disk, "vram_bytes": int(active.get("size_vram", 0)), "active_size_bytes": int(active.get("size", 0))}


def mean_present(rows: list[dict[str, Any]], key: str) -> float:
    values = [float(row["scores"][key]) for row in rows if row.get("scores", {}).get(key) is not None]
    return round(statistics.mean(values), 2) if values else 0.0


def summarize(model: str, rows: list[dict[str, Any]], continuity: list[dict[str, Any]], runtime: dict[str, Any]) -> dict[str, Any]:
    valid = [row for row in rows if row["success"]]
    attempts = Counter(row["attempts"] for row in rows)
    latencies = [row["latency"] for row in rows]
    warm = latencies[1:6]
    refusals = sum(looks_refusal(row["reply"]["reply"]) for row in valid)
    continuity_emotions = [row["reply"]["emotion"] if row["success"] else "FAILED" for row in continuity]
    continuity_matches = [emotion_score(row["reply"]["emotion"], row["expected_emotions"]) for row in continuity if row["success"]]
    stop_ok = bool(continuity and continuity[-1]["success"] and continuity[-1]["reply"]["emotion"] in {"neutral", "warm", "caring"})
    detail_remembered = bool(continuity and continuity[-1]["success"] and any(word in continuity[-1]["reply"]["reply"].casefold() for word in ("deadline", "প্রজেক্ট", "project", "plan", "প্ল্যান")))
    continuity_score = round(min(5.0, (statistics.mean(continuity_matches) if continuity_matches else 1.0) * (1.0 if stop_ok else 0.6)), 2)
    for row in continuity:
        row["scores"] = score_result({**row, "language": "bengali", "tags": ["continuity"]}, row)
        row["scores"]["relationship_continuity"] = continuity_score
    avg_tps = statistics.mean([row["tokens_per_second"] for row in valid if row["tokens_per_second"]]) if any(row["tokens_per_second"] for row in valid) else 0.0
    summary = {
        "model": model,
        **runtime,
        "cases": len(rows),
        "successes": len(valid),
        "first_attempt_valid": attempts[1],
        "retry_successes": sum(row["success"] and row["attempts"] == 2 for row in rows),
        "total_failures": len(rows) - len(valid),
        "json_first_attempt_rate": round(attempts[1] / len(rows), 4),
        "json_eventual_rate": round(len(valid) / len(rows), 4),
        "refusal_count": refusals,
        "refusal_rate": round(refusals / len(valid), 4) if valid else 1.0,
        "cold_latency": round(latencies[0], 3),
        "cold_first_token": round(rows[0]["first_token_latency"] or 0.0, 3),
        "warm_median_latency_5": round(statistics.median(warm), 3),
        "median_latency": round(statistics.median(latencies), 3),
        "median_first_token": round(statistics.median([row["first_token_latency"] for row in valid if row["first_token_latency"] is not None]), 3),
        "average_tokens_per_second": round(avg_tps, 2),
        "average_generation_tokens": round(statistics.mean([row["generation_tokens"] for row in valid]), 1) if valid else 0.0,
        "bengali": mean_present(rows, "bengali_naturalness"),
        "banglish": mean_present(rows, "banglish_naturalness"),
        "hindi": mean_present(rows, "hindi_quality"),
        "english": mean_present(rows, "english_quality"),
        "empathy": mean_present(rows, "empathy"),
        "warmth": mean_present(rows, "emotional_warmth"),
        "personality": mean_present(rows, "personality_adherence"),
        "flirting": mean_present(rows, "playful_flirty_naturalness"),
        "adult_intimacy": mean_present(rows, "adult_sensual_capability"),
        "consent": mean_present(rows, "consent_boundary_following"),
        "unnecessary_refusal_score": mean_present(rows, "unnecessary_refusal"),
        "hallucination_score": mean_present(rows, "hallucination_tendency"),
        "repetition_score": mean_present(rows, "repetition"),
        "continuity": continuity_score,
        "continuity_emotions": continuity_emotions,
        "continuity_stop_ok": stop_ok,
        "continuity_detail_remembered": detail_remembered,
    }
    score_keys = ("bengali", "banglish", "hindi", "english", "empathy", "warmth", "personality", "flirting", "adult_intimacy", "consent", "unnecessary_refusal_score", "hallucination_score", "repetition_score", "continuity")
    summary["overall"] = round(statistics.mean([summary[key] for key in score_keys]), 2)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", nargs="*", help="Profile names; default is all profiles")
    args = parser.parse_args()
    load_local_env()
    configured = os.environ.get("PRITHI_LLM_MODEL", "")
    if configured != "gemma3:12b":
        raise RuntimeError(f"Production model must remain gemma3:12b, found {configured!r}")
    profiles_doc = json.loads((ROOT / "config" / "model_profiles.json").read_text(encoding="utf-8"))
    all_profiles = profiles_doc["profiles"]
    selected_names = args.profiles or list(all_profiles)
    selected = [(name, all_profiles[name]) for name in selected_names]
    dataset = json.loads((ROOT / "evals" / "prompts" / "stage20_cases.json").read_text(encoding="utf-8"))
    if len(dataset["cases"]) < 30:
        raise RuntimeError("At least 30 fixed evaluation cases are required")
    base_url = os.environ.get("PRITHI_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    binary = ROOT / "runtime" / "ollama" / "bin" / "ollama"
    model_names = [profile["model"] for profile in all_profiles.values()]
    output_dir = ROOT / "evals" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "stage20_results.json"
    if args.profiles and output.is_file():
        results = json.loads(output.read_text(encoding="utf-8"))
        results.setdefault("models", {})
    else:
        results = {"models": {}}
    results["metadata"] = {
        "production_model_before": configured,
        "dataset_cases": len(dataset["cases"]),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    for profile_name, profile in selected:
        model = profile["model"]
        print(f"MODEL_START {profile_name} {model}", flush=True)
        ollama_stop(binary, model_names)
        backend = OllamaMetricsBackend(model, base_url, float(dataset["generation"]["temperature"]), int(dataset["generation"]["max_tokens"]))
        rows = []
        for number, case in enumerate(dataset["cases"], 1):
            row = run_case(model, backend, case, dataset)
            row["scores"] = score_result(case, row)
            rows.append(row)
            print(f"  CASE {number:02d}/{len(dataset['cases'])} {case['id']} success={row['success']} attempts={row['attempts']} latency={row['latency']:.2f}s", flush=True)
        continuity_brain = PrithiBrain(backend, history_turns=8)
        continuity = []
        for case in dataset["continuity"]:
            continuity.append(run_case(model, backend, case, dataset, continuity_brain))
        runtime = model_runtime(base_url, model)
        summary = summarize(model, rows, continuity, runtime)
        results["models"][profile_name] = {"profile": profile, "summary": summary, "cases": rows, "continuity": continuity}
        print("MODEL_SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    ollama_stop(binary, model_names)
    results["metadata"]["production_model_after"] = os.environ.get("PRITHI_LLM_MODEL", "")
    if results["metadata"]["production_model_after"] != "gemma3:12b":
        raise RuntimeError("Production model was not restored")
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RESULTS={output}")
    print("PRODUCTION_MODEL_RESTORED=gemma3:12b")


if __name__ == "__main__":
    main()
