import json
from typing import Any

import requests

from app.config.settings import get_settings
from app.llm.interfaces import LLMClient


class OpenRouterClient(LLMClient):
    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.llm_api_key
        self.model = self.settings.llm_model
        self.base_url = "https://openrouter.ai/api/v1"

    def complete_json(self, prompt: str) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://genai-recon.local",
            "X-Title": "Financial Reconciliation Platform",
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a financial data mapping assistant. Return valid JSON only.",
                },
                {
                    "role": "user",
                    "content": f"{prompt}\n\nReturn JSON only. No markdown formatting.",
                },
            ],
            "temperature": 0.1,
            "max_tokens": 4000,
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"]
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            return json.loads(content)

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"OpenRouter API error: {e}") from e
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            raise RuntimeError(f"Failed to parse LLM response: {e}") from e


class OpenRouterEmbeddingClient:
    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.llm_api_key
        self.model = self.settings.embedding_model
        self.base_url = "https://openrouter.ai/api/v1"

    def embed_text(self, text: str) -> list[float]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "input": text,
        }

        try:
            response = requests.post(
                f"{self.base_url}/embeddings",
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"OpenRouter embedding error: {e}") from e
