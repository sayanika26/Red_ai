import os
import json
import time
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
        raw_max_tokens = os.environ.get("PRITHI_LLM_MAX_TOKENS", "192").strip()
        try:
            self.max_tokens = int(raw_max_tokens)
        except ValueError as exc:
            raise LLMConfigurationError("PRITHI_LLM_MAX_TOKENS must be an integer") from exc
        if not 32 <= self.max_tokens <= 2048:
            raise LLMConfigurationError("PRITHI_LLM_MAX_TOKENS must be between 32 and 2048")
        self.streaming = os.environ.get("PRITHI_LLM_STREAMING", "false").strip().lower() in {"1", "true", "yes", "on"}
        self.last_first_token_time: float | None = None

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
        if self.provider == "ollama" and "qwen3" in self.model.casefold():
            return self._complete_ollama_native(messages)
        request_body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
            "stream": self.streaming,
        }
        if self.streaming:
            return self._complete_streaming(request_body)
        try:
            response = httpx.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=request_body,
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

    def _complete_ollama_native(self, messages: list[dict[str, str]]) -> str:
        """Use Ollama's native controls to prevent Qwen thinking from consuming JSON output."""
        native_base = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        request_body = {
            "model": self.model,
            "messages": messages,
            "format": "json",
            "think": False,
            "stream": False,
            "keep_alive": os.environ.get("PRITHI_OLLAMA_KEEP_ALIVE", "10m").strip() or "10m",
            "options": {"temperature": 0.7, "num_predict": self.max_tokens},
        }
        try:
            response = httpx.post(
                f"{native_base}/api/chat",
                json=request_body,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["message"]["content"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise LLMProviderError(f"Ollama native generation failed: {exc}") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError("Ollama native response contained no text")
        return content

    def _complete_streaming(self, request_body: dict) -> str:
        started = time.perf_counter()
        self.last_first_token_time = None
        pieces: list[str] = []
        try:
            with httpx.stream(
                "POST",
                self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=request_body,
                timeout=self.timeout_seconds,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    payload = json.loads(data)
                    content = payload.get("choices", [{}])[0].get("delta", {}).get("content")
                    if content:
                        if self.last_first_token_time is None:
                            self.last_first_token_time = time.perf_counter() - started
                        pieces.append(content)
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(f"OpenAI-compatible streaming generation failed: {exc}") from exc
        result = "".join(pieces)
        if not result:
            raise LLMProviderError("Provider streaming response contained no text")
        return result
