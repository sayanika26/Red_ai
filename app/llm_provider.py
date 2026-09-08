import os
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


class LLMConfigurationError(RuntimeError):
    pass


class LLMProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str

    @classmethod
    def from_environment(cls) -> "LLMConfig":
        names = ("PRITHI_LLM_BASE_URL", "PRITHI_LLM_API_KEY", "PRITHI_LLM_MODEL")
        values = {name: os.environ.get(name, "").strip() for name in names}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise LLMConfigurationError(
                "Missing LLM configuration: " + ", ".join(missing)
                + ". Set all three PRITHI_LLM_* environment variables before launching chat."
            )
        return cls(values[names[0]].rstrip("/"), values[names[1]], values[names[2]])

    @property
    def provider(self) -> str:
        host = (urlparse(self.base_url).hostname or "").lower()
        return "ollama" if host in {"127.0.0.1", "localhost", "::1"} else "openai-compatible"


class OpenAICompatibleBackend:
    def __init__(self, config: LLMConfig, timeout_seconds: float = 120.0) -> None:
        self.config = config
        self.base_url = config.base_url
        self.endpoint = f"{self.base_url}/chat/completions"
        self.api_key = config.api_key
        self.model = config.model
        self.provider = config.provider
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "OpenAICompatibleBackend":
        return cls(LLMConfig.from_environment())

    @property
    def safe_info(self) -> dict[str, str]:
        return {"provider": self.provider, "base_url": self.base_url, "model": self.model}

    def verify_model_available(self) -> None:
        try:
            response = httpx.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=15.0,
            )
            response.raise_for_status()
            models = response.json().get("data", [])
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise LLMProviderError(f"Could not query provider model list: {exc}") from exc
        model_ids = {item.get("id") for item in models if isinstance(item, dict)}
        if self.model not in model_ids:
            raise LLMProviderError(
                f"Configured model '{self.model}' is not available from provider '{self.provider}'"
            )

    def complete(self, messages: list[dict[str, str]]) -> str:
        try:
            response = httpx.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "messages": messages, "temperature": 0.7, "response_format": {"type": "json_object"}},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(f"OpenAI-compatible generation failed: {exc}") from exc
        if not isinstance(content, str):
            raise LLMProviderError("Provider message content was not a string")
        return content
