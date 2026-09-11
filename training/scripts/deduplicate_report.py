#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path


def normalize(value: str) -> str:
    return re.sub(r"[^\w\u0980-\u09ff\u0900-\u097f]+", " ", value.casefold()).strip()


def signature(row: dict) -> str:
    return normalize(" ".join(item.get("content", "") for item in row.get("messages", []) if item.get("role") != "system"))


def token_jaccard(left: str, right: str) -> float:
    a, b = set(left.split()), set(right.split())
    return len(a & b) / len(a | b) if a | b else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Report exact and near duplicates; never deletes rows")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=.88)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    prompts: dict[str, list[str]] = {}
    replies: dict[str, list[str]] = {}
    signed = []
    for row in rows:
        row_id = row["id"]
        user = normalize(next(item["content"] for item in reversed(row["messages"]) if item["role"] == "user"))
        assistant = normalize(next(item["content"] for item in reversed(row["messages"]) if item["role"] == "assistant"))
        prompts.setdefault(user, []).append(row_id)
        replies.setdefault(assistant, []).append(row_id)
        signed.append((row_id, signature(row)))
    near = []
    for index, (left_id, left) in enumerate(signed):
        for right_id, right in signed[index + 1:]:
            sequence = SequenceMatcher(None, left, right).ratio()
            jaccard = token_jaccard(left, right)
            if max(sequence, jaccard) >= args.threshold:
                near.append({"left": left_id, "right": right_id, "sequence": round(sequence, 3), "token_jaccard": round(jaccard, 3)})
    report = {
        "dataset": str(args.dataset),
        "rows": len(rows),
        "exact_prompt_groups": [ids for text, ids in prompts.items() if text and len(ids) > 1],
        "exact_reply_groups": [ids for text, ids in replies.items() if text and len(ids) > 1],
        "near_duplicate_pairs": near,
        "action": "Review only; no rows were deleted or modified.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: len(value) if isinstance(value, list) else value for key, value in report.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
