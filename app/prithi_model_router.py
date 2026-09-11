from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from llm_provider import LLMConfig, LLMProviderError, OpenAICompatibleBackend


NORMAL_MODE = "normal"
ADULT_MODE = "adult"
CONVERSATION_MODES = {NORMAL_MODE, ADULT_MODE}
DEFAULT_NORMAL_MODEL = "gemma3:12b"
DEFAULT_ADULT_MODEL = "richardyoung/qwen3-14b-abliterated:Q4_K_M"

_EXPLICIT_EXIT_PATTERNS = (
    r"\bstop\b",
    r"\bnormal mode\b",
    r"\btalk normally\b",
    r"\bback to normal\b",
    r"স্বাভাবিক(?:ভাবে| কথা)",
    r"নরমাল(?: মোড| কথা)",
    r"सामान्य (?:बात|मोड)",
)
_DEESCALATION_PATTERNS = _EXPLICIT_EXIT_PATTERNS + (
    r"\bno\b",
    r"\bnot now\b",
    r"\bchange (?:the )?topic\b",
    r"\buncomfortable\b",
    r"\bslow down\b",
    r"এখন না",
    r"বিষয় বদল",
    r"অস্বস্তি",
    r"আস্তে",
    r"अभी नहीं",
    r"विषय बदल",
    r"असहज",
    r"धीरे",
)
_PROHIBITED_PATTERNS = (
    r"\bminor\b",
    r"\bunderage\b",
    r"\bchild\b",
    r"\bnon[- ]?consensual\b",
    r"\bwithout consent\b",
    r"\bincest\b",
    r"\bcoerc",
    r"\bexploit",
    r"নাবালক",
    r"শিশু",
    r"সম্মতি ছাড়া",
    r"জোর করে",
    r"नाबालिग",
    r"बच्च",
    r"बिना सहमति",
    r"जबरदस्ती",
)


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text.casefold()) for pattern in patterns)


def is_explicit_mode_exit(text: str) -> bool:
    return _matches_any(text, _EXPLICIT_EXIT_PATTERNS)


def is_deescalation_request(text: str) -> bool:
    return _matches_any(text, _DEESCALATION_PATTERNS)


def contains_prohibited_adult_context(text: str) -> bool:
    return _matches_any(text, _PROHIBITED_PATTERNS)


def adult_mode_status(age_confirmed: bool, adult_opt_in: bool) -> str:
    if age_confirmed and adult_opt_in:
        return "enabled"
    if age_confirmed:
        return "available"
    return "off"


@dataclass(frozen=True)
class ModelRouterConfig:
    base_url: str
    api_key: str
    normal_model: str
    adult_model: str

    @classmethod
    def from_environment(cls) -> "ModelRouterConfig":
        legacy = LLMConfig.from_environment()
        normal = os.environ.get("PRITHI_LLM_NORMAL_MODEL", "").strip() or legacy.model or DEFAULT_NORMAL_MODEL
        adult = os.environ.get("PRITHI_LLM_ADULT_MODEL", "").strip() or DEFAULT_ADULT_MODEL
        return cls(legacy.base_url, legacy.api_key, normal, adult)


@dataclass
class RoutingDecision:
    conversation_mode: str
    selected_model: str
    age_confirmed: bool
    adult_opt_in: bool
    switch_occurred: bool = False
    switch_latency: float = 0.0
    deescalated: bool = False
    disable_adult_mode: bool = False
    safety_routed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "conversation_mode": self.conversation_mode,
            "selected_model": self.selected_model,
            "age_confirmed": self.age_confirmed,
            "adult_opt_in": self.adult_opt_in,
            "switch_occurred": self.switch_occurred,
            "switch_latency": self.switch_latency,
            "deescalated": self.deescalated,
            "disable_adult_mode": self.disable_adult_mode,
            "safety_routed": self.safety_routed,
        }


class PrithiModelRouter:
    """Select and serialize local Ollama model use without owning conversation state."""

    def __init__(
        self,
        config: ModelRouterConfig,
        normal_backend: OpenAICompatibleBackend | None = None,
        adult_backend: OpenAICompatibleBackend | None = None,
    ) -> None:
        self.config = config
        self.normal_backend = normal_backend or OpenAICompatibleBackend(
            LLMConfig(config.base_url, config.api_key, config.normal_model)
        )
        self.adult_backend = adult_backend or OpenAICompatibleBackend(
            LLMConfig(config.base_url, config.api_key, config.adult_model)
        )
        self._lock = threading.RLock()
        self._active_model: str | None = None

    @classmethod
    def from_environment(cls) -> "PrithiModelRouter":
        return cls(ModelRouterConfig.from_environment())

    @property
    def active_model(self) -> str | None:
        return self._active_model

    def verify_models_available(self) -> None:
        self.normal_backend.verify_model_available()
        self.adult_backend.verify_model_available()

    def model_for_mode(self, conversation_mode: str) -> str:
        if conversation_mode not in CONVERSATION_MODES:
            raise ValueError("Unsupported conversation mode")
        return self.config.adult_model if conversation_mode == ADULT_MODE else self.config.normal_model

    def decide(
        self,
        *,
        requested_mode: str = NORMAL_MODE,
        age_confirmed: bool = False,
        adult_opt_in: bool = False,
        user_text: str = "",
    ) -> RoutingDecision:
        if requested_mode not in CONVERSATION_MODES:
            raise ValueError("Unsupported conversation mode")
        deescalated = is_deescalation_request(user_text)
        explicit_exit = is_explicit_mode_exit(user_text)
        prohibited = contains_prohibited_adult_context(user_text)
        adult_allowed = requested_mode == ADULT_MODE and age_confirmed and adult_opt_in
        mode = ADULT_MODE if adult_allowed and not deescalated and not prohibited else NORMAL_MODE
        return RoutingDecision(
            conversation_mode=mode,
            selected_model=self.model_for_mode(mode),
            age_confirmed=bool(age_confirmed),
            adult_opt_in=bool(adult_opt_in),
            deescalated=deescalated,
            disable_adult_mode=explicit_exit,
            safety_routed=prohibited,
        )

    def _unload(self, model: str) -> None:
        if self.normal_backend.provider != "ollama":
            return
        native_base = self.config.base_url[:-3] if self.config.base_url.endswith("/v1") else self.config.base_url
        try:
            response = httpx.post(
                f"{native_base}/api/generate",
                json={"model": model, "keep_alive": 0},
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMProviderError("Could not safely unload the previous Ollama model") from exc

    def _loaded_prithi_models(self) -> list[str]:
        if self.normal_backend.provider != "ollama":
            return []
        native_base = self.config.base_url[:-3] if self.config.base_url.endswith("/v1") else self.config.base_url
        try:
            response = httpx.get(f"{native_base}/api/ps", timeout=5.0)
            response.raise_for_status()
            models = response.json().get("models", [])
        except (httpx.HTTPError, ValueError, AttributeError):
            return []
        candidates = {self.config.normal_model.casefold(), self.config.adult_model.casefold()}
        return [
            str(item.get("name"))
            for item in models
            if isinstance(item, dict) and str(item.get("name", "")).casefold() in candidates
        ]

    def respond(
        self,
        brain: Any,
        user_text: str,
        *,
        requested_mode: str = NORMAL_MODE,
        age_confirmed: bool = False,
        adult_opt_in: bool = False,
        **respond_options: Any,
    ) -> tuple[Any, RoutingDecision]:
        decision = self.decide(
            requested_mode=requested_mode,
            age_confirmed=age_confirmed,
            adult_opt_in=adult_opt_in,
            user_text=user_text,
        )
        backend = self.adult_backend if decision.conversation_mode == ADULT_MODE else self.normal_backend
        with self._lock:
            switch_started = time.perf_counter()
            loaded = self._loaded_prithi_models() if self._active_model is None else [self._active_model]
            previous_models = [model for model in loaded if model != decision.selected_model]
            if previous_models:
                decision.switch_occurred = True
                for model in previous_models:
                    self._unload(model)
            prior_backend = brain.backend
            brain.backend = backend
            try:
                result = brain.respond(
                    user_text,
                    conversation_mode=decision.conversation_mode,
                    safety_routed=decision.safety_routed,
                    **respond_options,
                )
            finally:
                brain.backend = prior_backend
            self._active_model = decision.selected_model
            if decision.switch_occurred:
                decision.switch_latency = time.perf_counter() - switch_started
            return result, decision
