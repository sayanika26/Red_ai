from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path

from prithi_context import TurnContext


MOOD_FIELDS = ("warmth", "energy", "playfulness", "affection", "confidence", "curiosity", "romantic_tension", "sensual_tension", "vulnerability", "comfort")


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


@dataclass
class MoodState:
    warmth: float = .55
    energy: float = .50
    playfulness: float = .35
    affection: float = .30
    confidence: float = .60
    curiosity: float = .50
    romantic_tension: float = 0.0
    sensual_tension: float = 0.0
    vulnerability: float = .20
    comfort: float = .45

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


class MoodStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS mood_states(user_id TEXT PRIMARY KEY, state_json TEXT NOT NULL, updated_at REAL NOT NULL)")

    def load(self, user_id: str) -> MoodState:
        with closing(self._connect()) as db:
            row = db.execute("SELECT state_json, updated_at FROM mood_states WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            return MoodState()
        values = json.loads(row["state_json"])
        elapsed_hours = max(0.0, (time.time() - float(row["updated_at"])) / 3600)
        decay = min(.35, elapsed_hours * .015)
        defaults = MoodState().as_dict()
        return MoodState(**{key: _clamp(float(values.get(key, defaults[key])) + (defaults[key] - float(values.get(key, defaults[key]))) * decay) for key in MOOD_FIELDS})

    def save(self, user_id: str, mood: MoodState) -> None:
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO mood_states VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at", (user_id, json.dumps(mood.as_dict(), sort_keys=True), time.time()))


def update_mood(current: MoodState, context: TurnContext, strategy: str, *, adult_mode: bool = False) -> MoodState:
    target = MoodState(**current.as_dict())
    deltas = {key: 0.0 for key in MOOD_FIELDS}
    if context.user_emotion == "sad":
        deltas.update(warmth=.05, energy=-.04, comfort=.05, vulnerability=.025)
    if context.user_emotion == "playful":
        deltas.update(energy=.04, playfulness=.06, confidence=.02)
    if context.relationship_signal == "positive":
        deltas.update(warmth=.035, affection=.04, comfort=.025)
    if strategy == "deescalation":
        deltas.update(romantic_tension=-.10, sensual_tension=-.12, comfort=.03)
    elif strategy == "sensual_reciprocation" and adult_mode:
        deltas.update(romantic_tension=.04, sensual_tension=.04, affection=.02)
    elif context.intimacy_signal != "none" and adult_mode:
        deltas["romantic_tension"] = .025
    for key, delta in deltas.items():
        setattr(target, key, _clamp(getattr(target, key) + max(-.12, min(.08, delta))))
    return target


def blend_voice_style(style: dict[str, float], mood: MoodState) -> dict[str, float]:
    result = dict(style)
    mappings = {"warmth": mood.warmth, "energy": mood.energy, "playfulness": mood.playfulness, "intimacy": max(mood.affection, mood.romantic_tension), "tenderness": max(mood.comfort, mood.vulnerability)}
    for key, value in mappings.items():
        result[key] = round(max(0.0, min(1.0, float(result.get(key, value)) * .75 + value * .25)), 3)
    return result
