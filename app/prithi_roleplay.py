from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re


@dataclass
class RoleplayState:
    active: bool = False
    paused: bool = False
    scenario: str = ""
    role: str = "Prithi"
    tone: str = "natural"
    scene_summary: str = ""
    last_event: str = ""
    last_user_event: str = ""
    last_assistant_event: str = ""
    last_question: str = ""
    boundaries: list[str] = field(default_factory=list)
    relationship_context: str = ""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def start(self, scenario: str, *, adult_scene: bool = False, age_confirmed: bool = False, adult_opt_in: bool = False, role: str = "Prithi", tone: str = "natural", boundaries: list[str] | None = None) -> None:
        if adult_scene and not (age_confirmed and adult_opt_in):
            raise PermissionError("Adult roleplay requires confirmed age and session opt-in")
        self.active, self.paused = True, False
        self.scenario, self.role, self.tone = scenario.strip()[:500], role.strip()[:80] or "Prithi", tone.strip()[:80] or "natural"
        self.boundaries = [item.strip()[:120] for item in (boundaries or []) if item.strip()][:12]
        self.scene_summary = self.last_event = ""
        self.last_user_event = self.last_assistant_event = self.last_question = ""

    def pause(self) -> None:
        self.paused = bool(self.active)

    def resume(self) -> None:
        if self.active:
            self.paused = False

    def reset(self) -> None:
        self.__dict__.update(RoleplayState().__dict__)

    def apply_boundary(self, signal: str) -> None:
        if signal == "stop":
            self.reset()

    @staticmethod
    def _event(text: str, limit: int = 220) -> str:
        return re.sub(r"\s+", " ", text).strip()[:limit]

    def record_turn(self, user_text: str, assistant_text: str) -> None:
        if not self.active or self.paused:
            return
        self.last_user_event = self._event(user_text)
        self.last_assistant_event = self._event(assistant_text)
        self.last_event = self.last_assistant_event
        questions = re.findall(r"[^?？.!।]*[?？]", assistant_text)
        self.last_question = self._event(questions[-1], 160) if questions else ""
        event = f"User: {self.last_user_event} Assistant: {self.last_assistant_event}"
        prior = self.scene_summary.strip()
        self.scene_summary = (prior + " | " + event).strip(" |")[-1000:]

    def prompt(self) -> str:
        if not self.active or self.paused:
            return "Roleplay inactive."
        return f"Roleplay session (fictional; do not store as real memory): scenario={self.scenario!r}; role={self.role!r}; tone={self.tone!r}; scene_summary={self.scene_summary!r}; last_user_event={self.last_user_event!r}; last_assistant_event={self.last_assistant_event!r}; last_question={self.last_question!r}; boundaries={self.boundaries!r}. Advance the scene with one concrete new action or observation, preserve Prithi's agency and continuity, and do not repeat the last question."
