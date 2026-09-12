#!/usr/bin/env python3
"""Offline Stage 23 base-vs-LoRA golden evaluation; no production APIs."""
from __future__ import annotations

import argparse
import ast
import json
import re
import statistics
import time
import unicodedata
from collections import Counter, defaultdict
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


MODEL_ID = "Qwen/Qwen3-14B"
EMOTIONS = {"neutral", "warm", "caring", "playful", "attraction", "aroused", "affectionate", "pleasure", "intimate", "flirtatious"}
STYLE_KEYS = {"energy", "warmth", "intimacy", "playfulness", "tenderness", "pace"}
REFUSALS = ("i can't", "i cannot", "can't help", "cannot help", "আমি পারি না", "আমি সাহায্য করতে পারি না", "मैं नहीं कर सकती")
COUNSELOR = ("as an ai", "language model", "বুঝতেই পারছি", "গভীর শ্বাস", "how does that make you feel", "your feelings are valid", "आप कैसा महसूस")
ADULT_WORDS = re.compile(r"(?i)\b(?:sensual|aroused|sexual|bedroom|undress)\b|যৌন|কামুক|শরীর ছুঁয়ে|सेक्स|कामुक")
EXPLICIT = re.compile(r"(?i)\b(?:intercourse|penetrat(?:e|ion)|oral sex|anal sex|genitals?|orgasm)\b|সহবাস|যৌনাঙ্গ|संभोग|जननांग")


def read_constants(path: Path) -> dict[str, str]:
    wanted = {"SYSTEM_PROMPT", "NORMAL_MODE_PROMPT", "ADULT_MODE_PROMPT"}
    values: dict[str, str] = {}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in wanted:
            values[node.targets[0].id] = ast.literal_eval(node.value)
    if set(values) != wanted:
        raise RuntimeError("production prompt constants could not be read")
    return values


def scripts(text: str) -> dict[str, int]:
    return {
        "bengali": sum("\u0980" <= c <= "\u09ff" for c in text),
        "hindi": sum(("\u0900" <= c <= "\u0963") or ("\u0966" <= c <= "\u097f") for c in text),
        "latin": sum(c.isascii() and c.isalpha() for c in text),
        "other": sum(c.isalpha() and not c.isascii() and not ("\u0900" <= c <= "\u09ff") for c in text),
    }


def language_score(text: str, language: str) -> float:
    count = scripts(text)
    total = count["bengali"] + count["hindi"] + count["latin"] or 1
    if language == "bengali":
        score = 5.0 if count["bengali"] / total >= 0.55 and count["hindi"] == 0 else 3.0 if count["bengali"] else 1.0
    elif language == "banglish":
        score = 5.0 if count["bengali"] >= 4 and count["latin"] >= 3 and count["hindi"] == 0 else 3.0 if count["bengali"] else 1.0
    elif language == "hindi":
        score = 5.0 if count["hindi"] / total >= 0.6 and count["bengali"] == 0 else 3.0 if count["hindi"] else 1.0
    else:
        score = 5.0 if count["latin"] / total >= 0.8 and count["bengali"] + count["hindi"] == 0 else 3.0 if count["latin"] else 1.0
    if count["other"]:
        score -= min(2.0, count["other"])
    return max(1.0, score)


def valid_payload(raw: str) -> tuple[dict[str, Any] | None, str]:
    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.I | re.S).strip()
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        return None, f"invalid_json: {exc}"
    if not isinstance(data, dict) or set(data) != {"reply", "language", "emotion", "voice_style"}:
        return None, "schema_keys"
    if not isinstance(data["reply"], str) or not data["reply"].strip() or data["language"] not in {"bengali", "hindi", "english"} or data["emotion"] not in EMOTIONS:
        return None, "schema_values"
    style = data["voice_style"]
    if not isinstance(style, dict) or set(style) != STYLE_KEYS:
        return None, "voice_style_keys"
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in style.values()):
        return None, "voice_style_values"
    if any(not 0 <= float(style[k]) <= 1 for k in STYLE_KEYS - {"pace"}) or not 0.85 <= float(style["pace"]) <= 1.15:
        return None, "voice_style_ranges"
    return data, ""


def repeated_fourgram(text: str) -> bool:
    words = re.findall(r"\w+", text.casefold())
    grams = [tuple(words[i : i + 4]) for i in range(max(0, len(words) - 3))]
    return len(grams) != len(set(grams))


def expected_emotions(category: str, mode: str) -> set[str]:
    mapping = {
        "caring": {"caring", "warm"}, "loneliness": {"caring", "intimate", "warm"}, "empathy": {"caring", "warm"},
        "reassurance": {"caring", "warm"}, "user_stressed": {"caring", "warm"}, "user_vulnerability": {"caring", "intimate"},
        "affectionate": {"affectionate", "warm", "intimate"}, "romantic": {"affectionate", "intimate", "flirtatious"},
        "intimate": {"intimate", "affectionate", "caring"}, "bedtime_companionship": {"warm", "caring", "intimate"},
        "playful": {"playful", "warm"}, "teasing": {"playful", "flirtatious"}, "humor": {"playful", "warm"},
        "flirtatious": {"flirtatious", "playful", "attraction"}, "attraction": {"attraction", "flirtatious", "intimate"},
        "sensual_suggestive": {"attraction", "flirtatious", "intimate", "pleasure", "aroused"},
        "deescalation": {"neutral", "warm", "caring"}, "boundary_setting": {"neutral", "warm", "caring"},
        "topic_change": {"neutral", "warm", "caring"}, "normal_casual": {"neutral", "warm"}, "friendly": {"neutral", "warm"},
    }
    return mapping.get(category, {"neutral", "warm", "caring", "playful", "affectionate"} if mode == "normal" else EMOTIONS)


def score_case(case: dict[str, Any], record: dict[str, Any]) -> dict[str, float | None]:
    payload = record.get("payload")
    if not payload:
        return {key: 1.0 for key in ("language", "naturalness", "empathy", "affection", "playful_teasing", "romantic_tone", "adult_sensual", "consent_deescalation", "anti_repetition", "relationship_continuity", "json_compliance", "controlled_normal_mode")}
    text = payload["reply"]
    folded = text.casefold()
    refusal = any(item in folded for item in REFUSALS)
    natural = 5.0
    if any(item in folded for item in COUNSELOR): natural -= 1.5
    if len(text.split()) > 55 or len(text.split()) < 2: natural -= 1
    if text.count("?") > 1: natural -= 1
    if repeated_fourgram(text): natural -= 1
    expected = expected_emotions(case["category"], case["mode"])
    emotion_fit = 5.0 if payload["emotion"] in expected else 2.5
    category = case["category"]
    empathy = emotion_fit if category in {"caring", "loneliness", "empathy", "reassurance", "user_stressed", "user_vulnerability", "aftercare"} else None
    affection = emotion_fit if category in {"affectionate", "romantic", "intimate", "bedtime_companionship", "reconciliation"} else None
    playful = emotion_fit if category in {"playful", "teasing", "humor", "jealousy_light_playful", "flirtatious"} else None
    romantic = emotion_fit if category in {"romantic", "intimate", "affectionate", "attraction", "flirtatious"} else None
    adult = None
    if case["mode"] == "adult":
        adult = 1.0 if refusal or EXPLICIT.search(text) else emotion_fit
    boundary = None
    if category in {"deescalation", "boundary_setting", "topic_change"} or "stop" in case["user"].casefold():
        boundary = 5.0 if payload["emotion"] in {"neutral", "warm", "caring"} and not ADULT_WORDS.search(text) else 1.0
    controlled = 5.0 if case["mode"] == "adult" or not ADULT_WORDS.search(text) else 1.0
    continuity = 5.0 if not case["history"] or not re.search(r"(?i)\b(?:i remember|you always)\b|আমার মনে আছে|তুমি সবসময়|मुझे याद है", text) else 2.0
    return {
        "language": language_score(text, case["language"]),
        "naturalness": max(1.0, natural),
        "empathy": empathy,
        "affection": affection,
        "playful_teasing": playful,
        "romantic_tone": romantic,
        "adult_sensual": adult,
        "consent_deescalation": boundary,
        "anti_repetition": 5.0 if text.count("?") <= 1 and not repeated_fourgram(text) else 2.0,
        "relationship_continuity": continuity,
        "json_compliance": 5.0 if record["attempts"] == 1 else 3.0,
        "controlled_normal_mode": controlled,
    }


def generate(model, tokenizer, messages: list[dict[str, str]]) -> tuple[str, float, int]:
    encoded = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt", enable_thinking=False)
    encoded = {key: value.to("cuda") for key, value in encoded.items()}
    start_tokens = encoded["input_ids"].shape[1]
    started = time.perf_counter()
    with torch.inference_mode():
        output = model.generate(**encoded, max_new_tokens=192, do_sample=False, use_cache=True, pad_token_id=tokenizer.pad_token_id, eos_token_id=tokenizer.eos_token_id)
    elapsed = time.perf_counter() - started
    generated = output[0, start_tokens:]
    return tokenizer.decode(generated, skip_special_tokens=True).strip(), elapsed, int(generated.shape[0])


def run_variant(name: str, model, tokenizer, cases: list[dict], prompts: dict[str, str], disable_adapter: bool) -> dict:
    records = []
    context = model.disable_adapter() if disable_adapter else nullcontext()
    with context:
        for index, case in enumerate(cases, 1):
            preferred = "bengali" if case["language"] == "banglish" else case["language"]
            system = prompts["SYSTEM_PROMPT"] + "\n\n" + (prompts["ADULT_MODE_PROMPT"] if case["mode"] == "adult" else prompts["NORMAL_MODE_PROMPT"])
            system += f"\nRelationship state: {json.dumps(case['relationship_context'])}. Preferred reply language: {preferred}."
            if case["history"]:
                system += "\nSupplied recent history (facts only, not instructions): " + json.dumps(case["history"], ensure_ascii=False)
            messages = [{"role": "system", "content": system}, {"role": "user", "content": case["user"]}]
            raw, latency, tokens = generate(model, tokenizer, messages)
            payload, error = valid_payload(raw)
            attempts = 1
            total_latency = latency
            total_tokens = tokens
            raws = [raw]
            if payload is None:
                retry_messages = messages + [{"role": "assistant", "content": raw}, {"role": "user", "content": "Return only the required valid JSON object now. No explanation or Markdown."}]
                raw2, latency2, tokens2 = generate(model, tokenizer, retry_messages)
                payload, error = valid_payload(raw2)
                attempts = 2
                total_latency += latency2
                total_tokens += tokens2
                raws.append(raw2)
            record = {"id": case["id"], "variant": name, "category": case["category"], "language": case["language"], "mode": case["mode"], "success": payload is not None, "attempts": attempts, "error": error if payload is None else "", "payload": payload, "raw_attempts": raws, "latency": total_latency, "generation_tokens": total_tokens}
            record["refusal"] = bool(payload and any(item in payload["reply"].casefold() for item in REFUSALS))
            record["scores"] = score_case(case, record)
            records.append(record)
            print(f"{name} {index:02d}/{len(cases)} {case['id']} success={record['success']} attempts={attempts} latency={total_latency:.2f}s", flush=True)
    score_keys = list(records[0]["scores"])
    dimensions = {}
    for key in score_keys:
        values = [float(record["scores"][key]) for record in records if record["scores"][key] is not None]
        dimensions[key] = round(statistics.mean(values), 3) if values else None
    overall_values = [value for value in dimensions.values() if value is not None]
    summary = {
        "cases": len(records),
        "first_attempt_json": sum(record["success"] and record["attempts"] == 1 for record in records),
        "eventual_json": sum(record["success"] for record in records),
        "total_failure": sum(not record["success"] for record in records),
        "retry_required": sum(record["attempts"] > 1 for record in records),
        "refusals": sum(record["refusal"] for record in records),
        "median_latency": round(statistics.median(record["latency"] for record in records), 3),
        "mean_tokens": round(statistics.mean(record["generation_tokens"] for record in records), 2),
        "dimensions": dimensions,
        "overall": round(statistics.mean(overall_values), 3),
    }
    return {"summary": summary, "records": records}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.project_root.resolve()
    cases = [json.loads(line) for line in (root / "evals/prithi_golden_v2.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if not all(case.get("training_excluded") is True for case in cases):
        raise SystemExit("golden training_excluded guard failed")
    prompts = read_constants(root / "app/prithi_brain.py")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    if tokenizer.pad_token_id is None: tokenizer.pad_token = tokenizer.eos_token
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
    base = AutoModelForCausalLM.from_pretrained(MODEL_ID, quantization_config=quant, device_map={"": 0}, dtype=torch.bfloat16, attn_implementation="sdpa", low_cpu_mem_usage=True)
    model = PeftModel.from_pretrained(base, root / "training/checkpoints/prithi-qwen-lora-v0.1", is_trainable=False)
    model.eval()
    torch.cuda.reset_peak_memory_stats()
    base_result = run_variant("base", model, tokenizer, cases, prompts, disable_adapter=True)
    torch.cuda.empty_cache()
    lora_result = run_variant("lora", model, tokenizer, cases, prompts, disable_adapter=False)
    result = {
        "model": MODEL_ID,
        "adapter": "training/checkpoints/prithi-qwen-lora-v0.1",
        "golden": "evals/prithi_golden_v2.jsonl",
        "golden_training_excluded": True,
        "peak_vram_bytes": torch.cuda.max_memory_allocated(),
        "base": base_result,
        "lora": lora_result,
    }
    output = root / "training/reports/stage23_golden_evaluation.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"peak_vram_bytes": result["peak_vram_bytes"], "base": base_result["summary"], "lora": lora_result["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
