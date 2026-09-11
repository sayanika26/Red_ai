#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


SCORES = ("naturalness", "personality_fit", "language_quality", "emotional_quality", "repetition", "voice_suitability")


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def save_rows(path: Path, rows: list[dict]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def score_row(row: dict) -> None:
    print("Scores are 1–5; for repetition, 5 means varied/non-repetitive.")
    for name in SCORES:
        while True:
            value = input(f"{name} [1-5, blank to leave]: ").strip()
            if not value:
                break
            if value.isdigit() and 1 <= int(value) <= 5:
                row["review"]["scores"][name] = int(value)
                break
            print("Enter a number from 1 to 5.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Human review CLI for Prithi candidate JSONL")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--start-id")
    args = parser.parse_args()
    path = args.dataset.expanduser().resolve()
    rows = load_rows(path)
    started = args.start_id is None
    changed = False
    for row in rows:
        if not started:
            started = row["id"] == args.start_id
        if not started or row["review"]["status"] != "pending":
            continue
        print("\n" + "=" * 72)
        print(f"{row['id']} | {row['language']} | {row['mode']} | {row['category']}")
        for message in row["messages"]:
            if message["role"] != "system":
                print(f"{message['role'].upper()}: {message['content']}")
        action = input("[a]pprove, [r]eject, [e]dit assistant, [s]kip, [q]uit: ").strip().lower()
        if action == "q":
            break
        if action == "s" or not action:
            continue
        if action == "e":
            replacement = input("Replacement final assistant reply: ").strip()
            if not replacement:
                print("Empty replacement ignored.")
                continue
            for message in reversed(row["messages"]):
                if message["role"] == "assistant":
                    message["content"] = replacement
                    break
            row["review"]["status"] = "edited"
        elif action in {"a", "r"}:
            row["review"]["status"] = "approved" if action == "a" else "rejected"
        else:
            print("Unknown action; row left pending.")
            continue
        score_row(row)
        row["review"]["notes"] = input("Review notes [optional]: ").strip()
        save_rows(path, rows)
        changed = True
        print(f"Saved {row['id']} as {row['review']['status']}.")
    if changed:
        print(f"Review changes saved atomically to {path}")
    else:
        print("No review changes made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
