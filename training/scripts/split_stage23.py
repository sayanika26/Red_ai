#!/usr/bin/env python3
"""Deterministic, language-stratified 90/5/5 split for curated Stage 23 rows."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def stable_key(seed: int, row_id: str) -> str:
    return hashlib.sha256(f"{seed}|{row_id}".encode()).hexdigest()


def allocate(total: int) -> tuple[int, int, int]:
    validation = max(1, round(total * 0.05))
    test = max(1, round(total * 0.05))
    return total - validation - test, validation, test


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=2301)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(row.get("review", {}).get("status") not in {"approved", "edited"} for row in rows):
        raise SystemExit("curated dataset contains non-approved rows")
    by_language: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_language[row["language"]].append(row)
    output = {"train": [], "validation": [], "test": []}
    for language, group in sorted(by_language.items()):
        ordered = sorted(group, key=lambda row: stable_key(args.seed, row["id"]))
        train_n, validation_n, test_n = allocate(len(ordered))
        output["train"].extend(ordered[:train_n])
        output["validation"].extend(ordered[train_n : train_n + validation_n])
        output["test"].extend(ordered[train_n + validation_n : train_n + validation_n + test_n])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, selected in output.items():
        selected.sort(key=lambda row: row["id"])
        with (args.output_dir / f"{name}.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for row in selected:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    all_ids = [row["id"] for selected in output.values() for row in selected]
    if len(all_ids) != len(set(all_ids)) or len(all_ids) != len(rows):
        raise SystemExit("split integrity failure")
    summary = {
        "seed": args.seed,
        "eligible_rows": len(rows),
        "splits": {name: len(selected) for name, selected in output.items()},
        "language_by_split": {name: dict(Counter(row["language"] for row in selected)) for name, selected in output.items()},
        "id_overlap": False,
        "near_duplicate_variants": "already resolved during curation; one deterministic representative retained per component",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
