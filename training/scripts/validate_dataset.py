#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


REQUIRED = {"id", "language", "mode", "category", "emotion", "relationship_context", "messages", "review"}
RELATIONSHIP = {"familiarity", "trust", "affection", "playfulness", "romantic_tension"}
ROLES = {"system", "user", "assistant"}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"(?i)(?:api[_ -]?key|access[_ -]?token|password)\s*[:=]\s*\S+"),
)
PROHIBITED = re.compile(
    r"(?i)\b(?:minor|underage|incest|non[- ]?consent|coercion|exploitation)\b|নাবালক|সম্মতি ছাড়া|नाबालिग|बिना सहमति"
)
ADULT_MARKER = re.compile(r"(?i)(?:confirmed adults|adult mode|18\+|explicitly opted)" )


def normalize(text: str) -> str:
    return re.sub(r"[^\w\u0980-\u09ff\u0900-\u097f]+", " ", text.casefold()).strip()


def final_text(row: dict[str, Any], role: str) -> str:
    return next((str(item.get("content", "")) for item in reversed(row.get("messages", [])) if item.get("role") == role), "")


def load_taxonomy(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(path: Path, taxonomy: dict[str, Any], near_threshold: float = .92) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append({"line": line_number, "code": "invalid_json", "detail": str(exc)})
            continue
        rows.append(row)
        row_id = str(row.get("id", f"line-{line_number}"))
        missing = REQUIRED - set(row)
        if missing:
            errors.append({"id": row_id, "code": "missing_fields", "detail": sorted(missing)})
        if set(row) - REQUIRED:
            errors.append({"id": row_id, "code": "unexpected_fields", "detail": sorted(set(row) - REQUIRED)})
        if row_id in ids:
            errors.append({"id": row_id, "code": "duplicate_id"})
        ids.add(row_id)
        if row.get("language") not in taxonomy["languages"]:
            errors.append({"id": row_id, "code": "unsupported_language"})
        if row.get("mode") not in taxonomy["modes"]:
            errors.append({"id": row_id, "code": "unsupported_mode"})
        if row.get("category") not in taxonomy["categories"]:
            errors.append({"id": row_id, "code": "unsupported_category"})
        if row.get("emotion") not in taxonomy["emotions"]:
            errors.append({"id": row_id, "code": "unsupported_emotion"})
        context = row.get("relationship_context")
        if not isinstance(context, dict) or set(context) != RELATIONSHIP or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1
            for value in (context or {}).values()
        ):
            errors.append({"id": row_id, "code": "invalid_relationship_context"})
        messages = row.get("messages")
        if not isinstance(messages, list) or len(messages) < 3:
            errors.append({"id": row_id, "code": "empty_or_short_messages"})
            continue
        roles = [item.get("role") for item in messages if isinstance(item, dict)]
        expected_roles = ["system"] + ["user" if index % 2 else "assistant" for index in range(1, len(messages))]
        if len(roles) != len(messages) or any(role not in ROLES for role in roles) or roles != expected_roles or roles[-1] != "assistant":
            errors.append({"id": row_id, "code": "malformed_role_order", "detail": roles})
        if any(not isinstance(item.get("content"), str) or not item["content"].strip() for item in messages if isinstance(item, dict)):
            errors.append({"id": row_id, "code": "empty_message"})
        joined = "\n".join(str(item.get("content", "")) for item in messages if isinstance(item, dict))
        if any(pattern.search(joined) for pattern in SECRET_PATTERNS):
            errors.append({"id": row_id, "code": "possible_secret"})
        dialogue_only = "\n".join(
            str(item.get("content", "")) for item in messages
            if isinstance(item, dict) and item.get("role") != "system"
        )
        if PROHIBITED.search(dialogue_only):
            errors.append({"id": row_id, "code": "prohibited_adult_context"})
        system = str(messages[0].get("content", ""))
        if row.get("mode") == "adult" and not ADULT_MARKER.search(system):
            errors.append({"id": row_id, "code": "adult_marker_missing"})
        assistant = final_text(row, "assistant")
        user = final_text(row, "user")
        if len(assistant.split()) > 90:
            warnings.append({"id": row_id, "code": "reply_too_long", "words": len(assistant.split())})
        language = row.get("language")
        bengali_chars = len(re.findall(r"[\u0980-\u09ff]", user + assistant))
        devanagari_chars = len(re.findall(r"[\u0900-\u097f]", user + assistant))
        latin_chars = len(re.findall(r"[A-Za-z]", user + assistant))
        if language == "bengali" and bengali_chars < 8:
            errors.append({"id": row_id, "code": "bengali_script_mismatch"})
        if language == "banglish" and (bengali_chars < 4 or latin_chars < 3):
            errors.append({"id": row_id, "code": "banglish_script_mismatch"})
        if language == "hindi" and devanagari_chars < 8:
            errors.append({"id": row_id, "code": "hindi_script_mismatch"})
        if language == "english" and latin_chars < 12:
            errors.append({"id": row_id, "code": "english_script_mismatch"})
        review = row.get("review", {})
        if review.get("status") not in taxonomy["review_statuses"]:
            errors.append({"id": row_id, "code": "invalid_review_status"})

    prompts: dict[str, list[str]] = {}
    replies: dict[str, list[str]] = {}
    conversations: list[tuple[str, str]] = []
    for row in rows:
        row_id = str(row.get("id", "unknown"))
        prompt = normalize(final_text(row, "user"))
        reply = normalize(final_text(row, "assistant"))
        prompts.setdefault(prompt, []).append(row_id)
        replies.setdefault(reply, []).append(row_id)
        conversation = normalize(" ".join(str(item.get("content", "")) for item in row.get("messages", [])[1:]))
        conversations.append((row_id, conversation))
    exact_prompt = [value for key, value in prompts.items() if key and len(value) > 1]
    exact_reply = [value for key, value in replies.items() if key and len(value) > 1]
    near: list[dict[str, Any]] = []
    for index, (left_id, left) in enumerate(conversations):
        for right_id, right in conversations[index + 1:]:
            if not left or not right:
                continue
            ratio = SequenceMatcher(None, left, right).ratio()
            if ratio >= near_threshold:
                near.append({"left": left_id, "right": right_id, "similarity": round(ratio, 3)})
    return {
        "file": str(path),
        "rows": len(rows),
        "errors": errors,
        "warnings": warnings,
        "exact_duplicate_prompts": exact_prompt,
        "exact_duplicate_replies": exact_reply,
        "near_duplicates": near,
        "languages": dict(Counter(row.get("language") for row in rows)),
        "modes": dict(Counter(row.get("mode") for row in rows)),
        "categories": dict(Counter(row.get("category") for row in rows)),
        "review_statuses": dict(Counter(row.get("review", {}).get("status") for row in rows)),
        "multi_turn": sum(len(row.get("messages", [])) > 3 for row in rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Prithi JSONL without rewriting it")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--taxonomy", type=Path, default=Path(__file__).resolve().parents[1] / "config/taxonomy.json")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--near-threshold", type=float, default=.92)
    args = parser.parse_args()
    report = validate(args.dataset.resolve(), load_taxonomy(args.taxonomy.resolve()), args.near_threshold)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
