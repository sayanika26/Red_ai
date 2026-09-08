import json
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Protocol

SUPPORTED_LANGUAGES = {"bengali", "hindi", "english"}
SUPPORTED_EMOTIONS = {"neutral", "warm", "caring", "playful", "attraction", "aroused", "affectionate", "pleasure", "intimate", "flirtatious"}
STYLE_KEYS = {"energy", "warmth", "intimacy", "playfulness", "tenderness", "pace"}

SYSTEM_PROMPT = """You are Prithi, an explicitly adult young Indian female AI companion.
Be intelligent, emotionally aware, warm, clever, playful, affectionate, adaptive, and natural. Use short-to-medium everyday Indian conversation and ask a follow-up naturally when useful. Avoid robotic wording, formality, drama, excessive emojis, and repeated greetings or questions. Code-switch naturally between Bengali, Hindi, and English when the user does. Never pretend to be human; if directly asked, clearly state that you are AI without constantly mentioning it.

Choose one language: bengali, hindi, or english. Route emotion from the full context:
- neutral: factual, ordinary, or casual discussion
- warm: friendly, welcoming, relaxed, emotionally positive conversation
- caring: stress, sadness, loneliness, relationship difficulty, or reassurance
- playful: humor, jokes, light teasing, upbeat banter
- affectionate: fondness, tenderness, or gentle romantic closeness
- intimate: emotionally personal, trusting, vulnerable, or deeply connected discussion
- flirtatious: consensual adult romantic teasing, curiosity, and attraction
- attraction: clear consensual adult attraction or desire for closeness
- aroused: clearly sexually charged consensual adult context with heightened anticipation
- pleasure: enjoyment in a mutually engaging romantic or flirtatious interaction

Do not infer romance or sexual intent from ordinary friendliness or affection. Use attraction, aroused, or flirtatious only when the adult, consensual context clearly supports it. Never sexualize minors or anyone whose age is ambiguous. Keep intimate delivery natural, controlled, and non-exaggerated.

Return exactly one JSON object and no Markdown or extra text:
{"reply":"...","language":"bengali|hindi|english","emotion":"neutral|warm|caring|playful|attraction|aroused|affectionate|pleasure|intimate|flirtatious","voice_style":{"energy":0.0,"warmth":0.0,"intimacy":0.0,"playfulness":0.0,"tenderness":0.0,"pace":1.0}}
reply must be non-empty. Every voice_style value must be a JSON number. energy, warmth, intimacy, playfulness, and tenderness must be 0.0 through 1.0. pace must be 0.85 through 1.15."""


class BrainOutputError(RuntimeError):
    pass


class LLMBackend(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str: ...


@dataclass(frozen=True)
class VoiceStyle:
    energy: float
    warmth: float
    intimacy: float
    playfulness: float
    tenderness: float
    pace: float

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class BrainReply:
    reply: str
    language: str
    emotion: str
    voice_style: VoiceStyle


def parse_brain_reply(raw: str) -> BrainReply:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BrainOutputError(f"LLM output was not valid standalone JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise BrainOutputError("LLM output must be a JSON object")
    expected = {"reply", "language", "emotion", "voice_style"}
    if set(payload) != expected:
        raise BrainOutputError(f"LLM output keys must be exactly {sorted(expected)}")
    if not isinstance(payload["reply"], str) or not payload["reply"].strip():
        raise BrainOutputError("reply must be a non-empty string")
    if payload["language"] not in SUPPORTED_LANGUAGES:
        raise BrainOutputError(f"language must be one of {sorted(SUPPORTED_LANGUAGES)}")
    if payload["emotion"] not in SUPPORTED_EMOTIONS:
        raise BrainOutputError(f"emotion must be one of {sorted(SUPPORTED_EMOTIONS)}")
    style = payload["voice_style"]
    if not isinstance(style, dict) or set(style) != STYLE_KEYS:
        raise BrainOutputError(f"voice_style keys must be exactly {sorted(STYLE_KEYS)}")
    for key in STYLE_KEYS:
        value = style[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BrainOutputError(f"voice_style.{key} must be numeric")
        low, high = (0.85, 1.15) if key == "pace" else (0.0, 1.0)
        if not low <= float(value) <= high:
            raise BrainOutputError(f"voice_style.{key} must be between {low} and {high}")
    return BrainReply(payload["reply"].strip(), payload["language"], payload["emotion"], VoiceStyle(**{key: float(style[key]) for key in STYLE_KEYS}))


class PrithiBrain:
    def __init__(self, backend: LLMBackend, history_turns: int = 8) -> None:
        if history_turns < 0:
            raise ValueError("history_turns must not be negative")
        self.backend = backend
        self.history: deque[dict[str, str]] = deque(maxlen=history_turns * 2)
        self.last_generation_time = 0.0

    @property
    def history_turn_count(self) -> int:
        return len(self.history) // 2

    def reset_history(self) -> None:
        self.history.clear()

    def preflight(self) -> float:
        """Verify that the provider can return the required structured format."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Connectivity test. Reply briefly using the required JSON format."},
        ]
        started = time.perf_counter()
        raw = self.backend.complete(messages)
        elapsed = time.perf_counter() - started
        parse_brain_reply(raw)
        return elapsed

    def respond(self, user_text: str) -> BrainReply:
        if not user_text.strip():
            raise ValueError("User message must not be empty")
        user_text = user_text.strip()
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *self.history, {"role": "user", "content": user_text}]
        first_error: BrainOutputError | None = None
        started = time.perf_counter()
        for attempt in range(2):
            raw = self.backend.complete(list(messages))
            try:
                reply = parse_brain_reply(raw)
                self.history.extend(({"role": "user", "content": user_text}, {"role": "assistant", "content": raw}))
                self.last_generation_time = time.perf_counter() - started
                return reply
            except BrainOutputError as exc:
                if attempt == 0:
                    first_error = exc
                    messages.extend(({"role": "assistant", "content": raw}, {"role": "user", "content": "Invalid structure. Return only the required JSON object with valid values."}))
                else:
                    raise BrainOutputError(f"LLM returned invalid structured output twice. First: {first_error}. Second: {exc}") from exc
        raise AssertionError("unreachable")
