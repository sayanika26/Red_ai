from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class RoleplayState:
    active: bool = False
    paused: bool = False
    scenario: str = ""
    role: str = "Prithi"
    tone: str = "natural"
    scene_summary: str = ""
    last_event: str = ""
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

    def prompt(self) -> str:
        if not self.active or self.paused:
            return "Roleplay inactive."
        return f"Roleplay session (fictional; do not store as real memory): scenario={self.scenario!r}; role={self.role!r}; tone={self.tone!r}; scene_summary={self.scene_summary!r}; last_event={self.last_event!r}; boundaries={self.boundaries!r}. Preserve Prithi's agency and continuity."
