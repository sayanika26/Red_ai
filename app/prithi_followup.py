from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass


@dataclass
class SilenceFollowup:
    asked_at: float | None = None
    sent: bool = False
    language: str = "english"
    seed: str = ""

    def note_user_activity(self) -> None:
        self.asked_at = None
        self.sent = False
        self.seed = ""

    def note_reply(self, reply: str, language: str, now: float | None = None) -> None:
        if len(re.findall(r"[?？]", reply)) == 1:
            self.asked_at = time.monotonic() if now is None else now
            self.sent = False
            self.language = language if language in {"bengali", "hindi", "english"} else "english"
            self.seed = reply
        else:
            self.note_user_activity()

    def take_if_due(self, timeout_seconds: float, now: float | None = None) -> str | None:
        current = time.monotonic() if now is None else now
        if timeout_seconds <= 0 or self.asked_at is None or self.sent or current - self.asked_at < timeout_seconds:
            return None
        choices = {
            "bengali": ("হুম? ভাবনায় হারিয়ে গেলে?", "তাড়া নেই... আমি এখানেই আছি।"),
            "hindi": ("हम्म? सोच में खो गए?", "कोई जल्दी नहीं... मैं यहीं हूँ।"),
            "english": ("Hmm? Lost in thought?", "No rush... I’m here."),
        }[self.language]
        index = int(hashlib.sha256(self.seed.encode("utf-8")).hexdigest()[:8], 16) % len(choices)
        self.sent = True
        return choices[index]
