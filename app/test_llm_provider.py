import os
import unittest
from unittest.mock import Mock, patch

import httpx

from llm_provider import LLMConfig, LLMProviderError, OpenAICompatibleBackend


class ProviderTests(unittest.TestCase):
    def config(self, model="model-a", base_url="http://127.0.0.1:11434/v1"):
        return LLMConfig(base_url, "local-placeholder", model)

    def models_response(self, *model_ids):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"data": [{"id": model_id} for model_id in model_ids]}
        return response

    def test_model_can_change_using_environment_only(self):
        environment = {
            "PRITHI_LLM_BASE_URL": "http://127.0.0.1:11434/v1",
            "PRITHI_LLM_API_KEY": "ollama",
            "PRITHI_LLM_MODEL": "replacement-model",
        }
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(LLMConfig.from_environment().model, "replacement-model")

    @patch("llm_provider.httpx.get")
    def test_unknown_profile_model_is_accepted_when_provider_serves_it(self, mock_get):
        mock_get.return_value = self.models_response("future-model")
        OpenAICompatibleBackend(self.config("future-model")).verify_model_available()

    @patch("llm_provider.httpx.get")
    def test_missing_ollama_model_has_clean_error(self, mock_get):
        mock_get.return_value = self.models_response("gemma3:12b")
        with self.assertRaisesRegex(LLMProviderError, "not available"):
            OpenAICompatibleBackend(self.config("missing-model")).verify_model_available()

    @patch("llm_provider.httpx.get")
    def test_invalid_provider_url_fails_safely(self, mock_get):
        request = httpx.Request("GET", "http://bad.invalid/v1/models")
        mock_get.side_effect = httpx.ConnectError("connection refused", request=request)
        with self.assertRaisesRegex(LLMProviderError, "Could not query"):
            OpenAICompatibleBackend(self.config(base_url="http://bad.invalid/v1")).verify_model_available()


if __name__ == "__main__":
    unittest.main(verbosity=2)
