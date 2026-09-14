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

    def feedback_recent(self, user_id: str, *, positive: bool) -> bool:
        """Apply explicit meta-feedback to the latest established preference."""
        with closing(self._connect()) as db, db:
            row = db.execute(
                "SELECT id,confidence,positive_count,negative_count FROM learned_behaviors WHERE user_id=? AND confidence>=.35 ORDER BY updated_at DESC,id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            if not row:
                return False
            delta = .08 if positive else -.14
            db.execute(
                "UPDATE learned_behaviors SET confidence=?,positive_count=?,negative_count=?,updated_at=? WHERE id=?",
                (max(.05, min(.95, float(row["confidence"]) + delta)), int(row["positive_count"]) + (1 if positive else 0), int(row["negative_count"]) + (0 if positive else 1), _now(), row["id"]),
            )
            return True

    def list_for_user(self, user_id: str) -> list[LearnedBehavior]:
        with closing(self._connect()) as db:
            rows = db.execute("SELECT type,scope,context_tags,strategy,example_style,confidence,positive_count,negative_count,created_at,updated_at FROM learned_behaviors WHERE user_id=? ORDER BY updated_at DESC,id DESC", (user_id,)).fetchall()
        return [LearnedBehavior(**{**dict(row), "context_tags": json.loads(row["context_tags"])}) for row in rows]

    def relevant(
        self,
        user_id: str,
        tags: list[str],
        limit: int = 3,
        *,
        min_relevance: float = .62,
    ) -> list[LearnedBehavior]:
        with closing(self._connect()) as db:
            rows = db.execute("SELECT type,scope,context_tags,strategy,example_style,confidence,positive_count,negative_count,created_at,updated_at FROM learned_behaviors WHERE user_id=? AND confidence>=.35 ORDER BY confidence DESC,updated_at DESC LIMIT 40", (user_id,)).fetchall()
        wanted = {tag.casefold() for tag in tags}
        values = [LearnedBehavior(**{**dict(row), "context_tags": json.loads(row["context_tags"])}) for row in rows]
        now = datetime.now(timezone.utc)

        def relevance(item: LearnedBehavior) -> float:
            item_tags = {tag.casefold() for tag in item.context_tags}
            overlap = wanted.intersection(item_tags)
            if not overlap:
                return 0.0
            metadata = {"bengali", "hindi", "english"}
            metadata.update(tag for tag in item_tags.union(wanted) if tag.startswith(("mode:", "roleplay:", "relationship:")))
            if item.type != "language_style" and item_tags - metadata and not overlap.difference(metadata):
                return 0.0
            item_languages = item_tags.intersection({"bengali", "hindi", "english"})
            wanted_languages = wanted.intersection({"bengali", "hindi", "english"})
            if item_languages and wanted_languages and item_languages != wanted_languages:
                return 0.0
            item_modes = {tag for tag in item_tags if tag.startswith("mode:")}
            wanted_modes = {tag for tag in wanted if tag.startswith("mode:")}
            if item_modes and wanted_modes and item_modes != wanted_modes:
                return 0.0
            romantic = any(marker in (" ".join(item_tags) + " " + item.example_style.casefold()) for marker in ("romantic", "sensual", "flirt", "intimate"))
            current_is_intimate = bool(wanted.intersection({"explicit_invitation", "affectionate", "intimate", "mode:adult", "roleplay:adult"}))
            if romantic and not current_is_intimate:
                return 0.0
            overlap_score = len(overlap) / max(1, min(len(item_tags), len(wanted)))
            feedback = (item.positive_count + 1) / (item.positive_count + item.negative_count + 2)
            try:
                age_days = max(0.0, (now - datetime.fromisoformat(item.updated_at)).total_seconds() / 86400)
            except (TypeError, ValueError):
                age_days = 365.0
            recency = 1.0 / (1.0 + age_days / 90.0)
            return .55 * overlap_score + .25 * item.confidence + .12 * feedback + .08 * recency

        ranked = sorted(((relevance(item), item) for item in values), key=lambda pair: pair[0], reverse=True)
        selected: list[LearnedBehavior] = []
        seen_types: set[str] = set()
        for score, item in ranked:
            if score < min_relevance or item.type in seen_types:
                continue
            selected.append(item)
            seen_types.add(item.type)
            if len(selected) >= max(0, limit):
                break
        return selected


def learning_signal(user_text: str, context: TurnContext, strategy: str) -> tuple[str, str, bool] | None:
    signals = learning_signals(user_text, context, strategy)
    return signals[0] if signals else None


def learning_signals(user_text: str, context: TurnContext, strategy: str) -> list[tuple[str, str, bool]]:
    low = user_text.casefold()
    if any(marker in low for marker in ("password", "api key", "sexual", "sensual detail", "যৌন", "নগ্ন", "पासवर्ड")):
        return []
    negative = any(marker in low for marker in ("পছন্দ না", "এভাবে না", "too much", "don't reply", "मत", "अच्छा नहीं"))
    positive = any(marker in low for marker in ("ভালো লাগে", "এভাবেই", "perfect", "nice", "अच्छा लगा", "ऐसे ही"))
    signals: list[tuple[str, str, bool]] = []
    polarity = positive and not negative

    if any(marker in low for marker in ("banglish", "বাংলিশ", "benglish")):
        signals.append(("language_style", "Use natural Bengali-English code-switching (Banglish).", not negative))
    if any(marker in low for marker in ("কম tease", "tease me lightly", "light teasing", "হালকা tease", "हल्का tease")):
        dislikes_light = any(marker in low for marker in ("light teasing পছন্দ না", "don't tease me lightly", "হালকা tease পছন্দ না"))
        signals.append(("teasing_intensity", "Keep teasing light and kind.", not dislikes_light))
    elif any(marker in low for marker in ("more teasing", "tease me more", "আরও tease", "বেশি tease")):
        signals.append(("teasing_intensity", "Use more playful teasing when the conversation is playful.", not negative))
    if any(marker in low for marker in ("just listen", "শুধু শুন", "advice দিও না", "no advice", "सलाह मत")):
        signals.append(("support_style", "When I seek support, listen and validate before offering advice.", not negative))
    if any(marker in low for marker in ("mirror my affection", "same affection", "আমার affection", "আমার আদর", "পাল্টা আদর")):
        signals.append(("affection_style", "Mirror clearly offered affection without escalating it.", not negative))
    if positive or negative:
        style = "Prefer concise natural " + context.language + " responses using " + strategy + "."
        signals.append(("response_preference", style, polarity))
    # Preserve order while avoiding duplicate type/style records from one turn.
    unique: dict[tuple[str, str], tuple[str, str, bool]] = {}
    for item in signals:
        unique[(item[0], item[1])] = item
    return list(unique.values())


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
