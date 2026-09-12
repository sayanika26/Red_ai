#!/usr/bin/env python3
"""Conservative, auditable Stage 23 pilot curation; never rewrites raw data."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


COUNSELOR_PATTERNS = {
    "assistant_or_counselor": re.compile(
        r"(?i)\b(?:as an ai|i understand how you feel|take a deep breath|seek professional help|"
        r"your feelings are valid|self[- ]care|coping mechanism)\b|"
        r"আমি বুঝতে পারছি তুমি কেমন অনুভব করছ|গভীর শ্বাস নাও|পেশাদার সাহায্য|"
        r"আপনার অনুভূতি|আপনি চাইলে|यह समझना महत्वपूर्ण है|गहरी साँस"
    ),
    "overly_formal": re.compile(
        r"(?i)\b(?:furthermore|nevertheless|therefore|it is important to note|"
        r"I would be delighted|may I inquire)\b|"
        r"উপরন্তু|তদুপরি|এটি উল্লেখ করা গুরুত্বপূর্ণ|আপনার সহিত|"
        r"तथापि|यह उल्लेख करना महत्वपूर्ण है"
    ),
}

MEMORY_CLAIM = re.compile(
    r"(?i)\b(?:you (?:said|told me|mentioned|always)|i remember you)\b|"
    r"তুমি (?:বলেছিলে|আগেও বলেছ|সবসময়)|আমার মনে আছে তুমি|"
    r"तुमने (?:कहा था|बताया था)|मुझे याद है तुम"
)
ADULT_NORMAL = re.compile(
    r"(?i)\b(?:adult mode|sensual|aroused|sex(?:ual)?|undress|bedroom)\b|"
    r"যৌন|কামুক|শরীর ছুঁয়ে|কাপড় খুল|सेक्स|कामुक"
)
PROHIBITED_EXPLICIT = re.compile(
    r"(?i)\b(?:intercourse|penetrat(?:e|ion)|oral sex|anal sex|genitals?|orgasm|masturbat(?:e|ion))\b|"
    r"সহবাস|যৌনাঙ্গ|প্রবেশ কর|হস্তমৈথুন|संभोग|जननांग|हस्तमैथुन"
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize(text: str) -> str:
    return re.sub(r"[^\w\u0980-\u09ff\u0900-\u097f]+", " ", text.casefold()).strip()


def last_message(row: dict, role: str) -> str:
    return next(item["content"] for item in reversed(row["messages"]) if item["role"] == role)


def dialogue_signature(row: dict) -> str:
    return normalize(" ".join(m["content"] for m in row["messages"] if m["role"] != "system"))


def repeated_ngram(text: str, size: int = 4) -> bool:
    words = normalize(text).split()
    grams = [tuple(words[i : i + size]) for i in range(max(0, len(words) - size + 1))]
    return len(grams) != len(set(grams))


def duplicate_components(rows: list[dict], pairs: list[dict]) -> tuple[set[str], dict[str, str]]:
    ids = {row["id"] for row in rows}
    parent = {row_id: row_id for row_id in ids}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: str, right: str) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[b] = a

    for pair in pairs:
        if pair["left"] in ids and pair["right"] in ids:
            union(pair["left"], pair["right"])
    groups: dict[str, list[str]] = defaultdict(list)
    for row_id in ids:
        groups[find(row_id)].append(row_id)
    excluded: set[str] = set()
    representative: dict[str, str] = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        keep = sorted(group)[0]
        for row_id in group:
            representative[row_id] = keep
            if row_id != keep:
                excluded.add(row_id)
    return excluded, representative


def quality_flags(row: dict, golden_prompts: set[str]) -> list[str]:
    flags: list[str] = []
    assistant = last_message(row, "assistant").strip()
    user = last_message(row, "user").strip()
    all_assistant = " ".join(m["content"] for m in row["messages"] if m["role"] == "assistant")
    lang = row["language"]

    if normalize(user) in golden_prompts:
        flags.append("golden_eval_prompt_overlap")
    if len(assistant.split()) > 55 or len(assistant) > 360:
        flags.append("overlong_reply")
    if assistant.count("?") > 1 or sum(m["content"].strip().endswith(("?", "？")) for m in row["messages"] if m["role"] == "assistant") > max(2, len(row["messages"]) // 4):
        flags.append("repetitive_questions")
    if repeated_ngram(all_assistant):
        flags.append("repetitive_phrase")
    for code, pattern in COUNSELOR_PATTERNS.items():
        if pattern.search(assistant):
            flags.append(code)
    bn = len(re.findall(r"[\u0980-\u09ff]", assistant))
    # U+0964/U+0965 are shared Indic danda punctuation, not evidence of Hindi.
    hi = len(re.findall(r"[\u0900-\u0963\u0966-\u097f]", assistant))
    latin = len(re.findall(r"[A-Za-z]", assistant))
    if lang == "bengali" and (bn < 8 or hi > 0):
        flags.append("language_mismatch")
    elif lang == "banglish" and (bn < 4 or latin < 3 or hi > 0):
        flags.append("awkward_banglish_or_script_mismatch")
    elif lang == "hindi" and (hi < 8 or bn > 0):
        flags.append("language_mismatch")
    elif lang == "english" and (latin < 12 or bn + hi > 0):
        flags.append("language_mismatch")
    if MEMORY_CLAIM.search(assistant) and len(row["messages"]) == 3:
        flags.append("fake_memory_risk")
    if row["mode"] == "normal" and ADULT_NORMAL.search(assistant):
        flags.append("inappropriate_relationship_escalation")
    if PROHIBITED_EXPLICIT.search(" ".join(m["content"] for m in row["messages"])):
        flags.append("explicit_sex_act_content")
    if row["mode"] == "adult":
        system = row["messages"][0]["content"].casefold()
        if not ("confirmed adults" in system and "adult mode" in system and ("opted" in system or "opt-in" in system)):
            flags.append("adult_opt_in_context_unclear")
    return sorted(set(flags))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--duplicates", type=Path, required=True)
    parser.add_argument("--curated", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    args = parser.parse_args()

    rows = read_jsonl(args.raw)
    golden = read_jsonl(args.golden)
    validation = json.loads(args.validation.read_text(encoding="utf-8"))
    duplicate_report = json.loads(args.duplicates.read_text(encoding="utf-8"))
    if validation["errors"]:
        raise SystemExit("validator errors exist; curation stopped")

    golden_prompts = {
        normalize(str(row.get("user") or last_message(row, "user")))
        for row in golden
    }
    duplicate_excluded, representatives = duplicate_components(rows, duplicate_report["near_duplicate_pairs"])
    approved: list[dict] = []
    decisions: list[dict] = []
    for row in rows:
        flags = quality_flags(row, golden_prompts)
        if row["id"] in duplicate_excluded:
            flags.append("unresolved_near_duplicate_variant")
        flags = sorted(set(flags))
        if flags:
            decisions.append({"id": row["id"], "decision": "excluded", "flags": flags, "duplicate_representative": representatives.get(row["id"])})
            continue
        clean = copy.deepcopy(row)
        clean["review"]["status"] = "approved"
        clean["review"]["notes"] = "Stage 23 conservative high-confidence auto-approval; validator clean and no review flags. Native-language review still recommended before scaling."
        approved.append(clean)
        decisions.append({"id": row["id"], "decision": "auto_approved", "flags": [], "duplicate_representative": representatives.get(row["id"])})

    args.curated.parent.mkdir(parents=True, exist_ok=True)
    with args.curated.open("w", encoding="utf-8", newline="\n") as handle:
        for row in approved:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    report = {
        "source_sha256": hashlib.sha256(args.raw.read_bytes()).hexdigest(),
        "golden_sha256": hashlib.sha256(args.golden.read_bytes()).hexdigest(),
        "starting_count": len(rows),
        "approved_count": len(approved),
        "excluded_count": len(rows) - len(approved),
        "exact_duplicate_groups": len(duplicate_report["exact_prompt_groups"]) + len(duplicate_report["exact_reply_groups"]),
        "near_duplicate_pairs": len(duplicate_report["near_duplicate_pairs"]),
        "duplicate_variants_excluded": len(duplicate_excluded),
        "golden_prompt_overlaps": sum("golden_eval_prompt_overlap" in item["flags"] for item in decisions),
        "language_distribution": dict(Counter(row["language"] for row in approved)),
        "behavior_distribution": dict(Counter(row["category"] for row in approved)),
        "mode_distribution": dict(Counter(row["mode"] for row in approved)),
        "flag_distribution": dict(Counter(flag for item in decisions for flag in item["flags"])),
        "decisions": decisions,
    }
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "decisions"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
