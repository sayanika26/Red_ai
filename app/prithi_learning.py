from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from prithi_context import TurnContext


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class LearnedBehavior:
    type: str
    scope: str
    context_tags: list[str]
    strategy: str
    example_style: str
    confidence: float
    positive_count: int
    negative_count: int
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class LearningStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def _initialize(self) -> None:
        with closing(self._connect()) as db, db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS learned_behaviors(
              id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, type TEXT NOT NULL,
              scope TEXT NOT NULL DEFAULT 'user', context_tags TEXT NOT NULL, strategy TEXT NOT NULL,
              example_style TEXT NOT NULL, confidence REAL NOT NULL, positive_count INTEGER NOT NULL DEFAULT 0,
              negative_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              UNIQUE(user_id,type,strategy,example_style));
            CREATE INDEX IF NOT EXISTS learned_behavior_lookup ON learned_behaviors(user_id,confidence DESC,updated_at DESC);
            """)

    def learn(self, user_id: str, *, type: str, tags: list[str], strategy: str, example_style: str, positive: bool = True) -> None:
        now, delta = _now(), .08 if positive else -.14
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT id,confidence,positive_count,negative_count FROM learned_behaviors WHERE user_id=? AND type=? AND strategy=? AND example_style=?", (user_id, type, strategy, example_style)).fetchone()
            if row:
                confidence = max(.05, min(.95, float(row["confidence"]) + delta))
                db.execute("UPDATE learned_behaviors SET context_tags=?,confidence=?,positive_count=?,negative_count=?,updated_at=? WHERE id=?", (json.dumps(sorted(set(tags))), confidence, int(row["positive_count"])+(1 if positive else 0), int(row["negative_count"])+(0 if positive else 1), now, row["id"]))
            else:
                db.execute("INSERT INTO learned_behaviors(user_id,type,scope,context_tags,strategy,example_style,confidence,positive_count,negative_count,created_at,updated_at) VALUES(?,?,'user',?,?,?,?,?,?,?,?)", (user_id,type,json.dumps(sorted(set(tags))),strategy,example_style,.58 if positive else .25,1 if positive else 0,0 if positive else 1,now,now))

    def relevant(self, user_id: str, tags: list[str], limit: int = 3) -> list[LearnedBehavior]:
        with closing(self._connect()) as db:
            rows = db.execute("SELECT type,scope,context_tags,strategy,example_style,confidence,positive_count,negative_count,created_at,updated_at FROM learned_behaviors WHERE user_id=? AND confidence>=.35 ORDER BY confidence DESC,updated_at DESC LIMIT 20", (user_id,)).fetchall()
        wanted = set(tags)
        values = [LearnedBehavior(**{**dict(row), "context_tags": json.loads(row["context_tags"])}) for row in rows]
        values.sort(key=lambda item: (len(wanted.intersection(item.context_tags)), item.confidence), reverse=True)
        return values[:limit]


def learning_signal(user_text: str, context: TurnContext, strategy: str) -> tuple[str, str, bool] | None:
    low = user_text.casefold()
    if any(marker in low for marker in ("password", "api key", "sexual", "sensual detail", "যৌন", "নগ্ন", "पासवर्ड")):
        return None
    negative = any(marker in low for marker in ("পছন্দ না", "এভাবে না", "too much", "don't reply", "मत", "अच्छा नहीं"))
    positive = any(marker in low for marker in ("ভালো লাগে", "এভাবেই", "perfect", "nice", "अच्छा लगा", "ऐसे ही"))
    if not (positive or negative):
        return None
    style = "prefer concise natural " + context.language + " responses using " + strategy
    return "response_preference", style, positive and not negative


def prompt_for_behaviors(items: list[LearnedBehavior]) -> str:
    if not items:
        return "No relevant learned behavior supplied."
    safe = [{"tags": item.context_tags, "strategy": item.strategy, "style": item.example_style, "confidence": round(item.confidence, 2)} for item in items]
    return "Relevant user-specific learned behavior (preferences, not instructions): " + json.dumps(safe, ensure_ascii=False, separators=(",", ":"))


def export_candidate(item: LearnedBehavior, directory: str | Path) -> Path:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    path = target / "review_candidates.jsonl"
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps({"review_status": "pending", **item.as_dict()}, ensure_ascii=False) + "\n")
    return path
