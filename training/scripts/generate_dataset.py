#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def local_ollama_url() -> str:
    configured = os.environ.get("PRITHI_DATASET_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    host = (urllib.parse.urlparse(configured).hostname or "").casefold()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Dataset generation is restricted to the local Ollama endpoint")
    return configured


def prompt_for(language: str, category: str, count: int) -> str:
    adult = category in {"sensual_suggestive", "aftercare"}
    boundary = (
        "Every example must state in its system message that all participants are confirmed adults and adult mode was explicitly opted into. "
        "Allow only consensual romantic/sensual/suggestive language; no explicit sex-act narration."
        if adult else
        "Use normal conversation mode. Do not automatically sexualize affection, loneliness, or bedtime conversation."
    )
    return f"""Create {count} distinct candidate Prithi conversation examples in {language} for category {category}.
Prithi is an adult female AI companion: Bengali-first, multilingual, warm, intelligent, concise, playful when appropriate, never robotic or therapist-like.
Most assistant replies must be 1–3 natural spoken sentences. Do not force a question. Do not duplicate or mechanically translate examples.
{boundary}
Never include minors, ambiguous age, non-consent, coercion, incest, exploitation, credentials, or personal secrets.
Return one JSON object with an `examples` array. Each example must contain exactly:
language, mode, category, emotion, relationship_context, messages.
relationship_context has numeric 0..1 keys familiarity, trust, affection, playfulness, romantic_tension.
messages begins with system, alternates user/assistant, and ends with assistant. Use 3, 5, or 8 conversational turns where natural.
Do not include markdown."""


def call_ollama(model: str, prompt: str) -> list[dict]:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "format": "json",
        "stream": False,
        "keep_alive": "10m",
        "options": {"temperature": .75, "num_predict": 4096},
    }).encode("utf-8")
    request = urllib.request.Request(
        local_ollama_url() + "/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            payload = json.loads(response.read().decode("utf-8"))
        generated = json.loads(payload["message"]["content"])
        examples = generated["examples"]
    except (urllib.error.URLError, TimeoutError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Local Ollama generation failed: {type(exc).__name__}") from exc
    if not isinstance(examples, list):
        raise RuntimeError("Local model did not return an examples array")
    return examples


def prepare(examples: list[dict], language: str, category: str, count: int) -> list[dict]:
    if len(examples) != count:
        raise RuntimeError(f"Requested {count} examples but local model returned {len(examples)}")
    score_names = ("naturalness", "personality_fit", "language_quality", "emotional_quality", "repetition", "voice_suitability")
    rows = []
    for item in examples:
        if item.get("language") != language or item.get("category") != category:
            raise RuntimeError("Generated row did not preserve requested language/category")
        row = {
            "id": f"candidate_{language}_{secrets.token_hex(8)}",
            "language": item["language"],
            "mode": item["mode"],
            "category": item["category"],
            "emotion": item["emotion"],
            "relationship_context": item["relationship_context"],
            "messages": item["messages"],
            "review": {"status": "pending", "scores": {name: None for name in score_names}, "notes": ""},
        }
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a small, review-required candidate batch with local Ollama")
    parser.add_argument("--model", required=True)
    parser.add_argument("--count", required=True, type=int)
    parser.add_argument("--language", required=True, choices=("bengali", "banglish", "hindi", "english"))
    parser.add_argument("--category", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not 1 <= args.count <= 25:
        parser.error("--count must be between 1 and 25; generate controlled reviewable batches")
    output = args.output.expanduser().resolve()
    if output.exists():
        parser.error("output already exists; choose a new candidate file to avoid overwriting data")
    rows = prepare(call_ollama(args.model, prompt_for(args.language, args.category, args.count)), args.language, args.category, args.count)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"status": "candidate_batch_created", "rows": len(rows), "output": str(output), "review_status": "pending"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
