#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert canonical Prithi rows without changing the source dataset")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--format", choices=("messages", "sharegpt"), required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; conversion never overwrites by default")
    rows = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            if args.format == "messages":
                converted = {"id": row["id"], "messages": row["messages"]}
            else:
                roles = {"system": "system", "user": "human", "assistant": "gpt"}
                converted = {
                    "id": row["id"],
                    "conversations": [{"from": roles[item["role"]], "value": item["content"]} for item in row["messages"]],
                }
            handle.write(json.dumps(converted, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"rows": len(rows), "format": args.format, "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
