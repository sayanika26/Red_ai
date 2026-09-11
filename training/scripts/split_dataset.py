#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path


def normalize(row: dict) -> str:
    text = " ".join(item.get("content", "") for item in row["messages"] if item["role"] != "system")
    return re.sub(r"[^\w\u0980-\u09ff\u0900-\u097f]+", " ", text.casefold()).strip()


def clusters(rows: list[dict], threshold: float) -> list[list[int]]:
    parent = list(range(len(rows)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[b] = a

    signatures = [normalize(row) for row in rows]
    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            if SequenceMatcher(None, signatures[left], signatures[right]).ratio() >= threshold:
                union(left, right)
    grouped: dict[int, list[int]] = {}
    for index in range(len(rows)):
        grouped.setdefault(find(index), []).append(index)
    return list(grouped.values())


def split_name(seed: int, ids: list[str]) -> str:
    digest = hashlib.sha256((str(seed) + "|" + "|".join(sorted(ids))).encode()).digest()
    value = int.from_bytes(digest[:8], "big") / 2**64
    if value < .90:
        return "train"
    if value < .95:
        return "validation"
    return "test"


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic 90/5/5 split with near-duplicate grouping")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=2201)
    parser.add_argument("--near-threshold", type=float, default=.90)
    parser.add_argument("--include-pending", action="store_true", help="For tooling tests only; curated splits should omit pending rows")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    all_rows = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [row for row in all_rows if args.include_pending or row["review"]["status"] in {"approved", "edited"}]
    if not rows:
        parser.error("no approved/edited rows available; complete human review before splitting")
    outputs = {name: args.output_dir / f"{name}.jsonl" for name in ("train", "validation", "test")}
    if not args.overwrite and any(path.exists() for path in outputs.values()):
        parser.error("split output exists; use --overwrite only when intentionally regenerating deterministic splits")
    assignments: dict[str, list[dict]] = {name: [] for name in outputs}
    for group in clusters(rows, args.near_threshold):
        name = split_name(args.seed, [rows[index]["id"] for index in group])
        assignments[name].extend(rows[index] for index in group)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, path in outputs.items():
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in sorted(assignments[name], key=lambda item: item["id"]):
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"seed": args.seed, "eligible_rows": len(rows), "splits": dict(Counter({name: len(value) for name, value in assignments.items()}))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
