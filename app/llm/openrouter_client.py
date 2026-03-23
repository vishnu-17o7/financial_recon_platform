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
        self.temperature = max(
            0.0,
            min(1.0, float(getattr(self.settings, "llm_temperature", 0.0))),
        )
        self.top_p = max(
            0.0,
            min(1.0, float(getattr(self.settings, "llm_top_p", 0.1))),
        )
        self.seed = int(getattr(self.settings, "llm_seed", 42))
        self.base_url = "https://openrouter.ai/api/v1"

    @staticmethod
    def _coerce_content(raw_content: Any) -> str:
        if isinstance(raw_content, str):
            return raw_content

        if isinstance(raw_content, list):
            chunks: list[str] = []
            for item in raw_content:
                if isinstance(item, str):
                    chunks.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    chunks.append(text)
            return "\n".join(chunks)

        if raw_content is None:
            return ""
        return str(raw_content)

    @staticmethod
    def _strip_fences(content: str) -> str:
        text = content.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

        return text.strip()

    @classmethod
    def _parse_json_payload(cls, raw_content: Any) -> dict[str, Any]:
        text = cls._strip_fences(cls._coerce_content(raw_content))
        if not text:
            raise json.JSONDecodeError("empty content", "", 0)

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            if (
                isinstance(parsed, list)
                and len(parsed) == 1
                and isinstance(parsed[0], dict)
            ):
                return parsed[0]
            raise json.JSONDecodeError("top-level JSON is not an object", text, 0)
        except json.JSONDecodeError:
            decoder = json.JSONDecoder()
            for idx, ch in enumerate(text):
                if ch not in "[{":
                    continue
                try:
                    candidate, _ = decoder.raw_decode(text[idx:])
                except json.JSONDecodeError:
                    continue

                if isinstance(candidate, dict):
                    return candidate
                if (
                    isinstance(candidate, list)
                    and len(candidate) == 1
                    and isinstance(candidate[0], dict)
                ):
                    return candidate[0]

            raise

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
                    "content": (
                        "You are a financial reconciliation assistant. "
                        "Return STRICT valid JSON object only. "
                        "Be concise and deterministic. "
                        "No markdown, no prose, no comments, no extra keys."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"{prompt}\n\n"
                        "STRICT OUTPUT RULES:\n"
                        "1) Return one JSON object only.\n"
                        "2) Keep reasons/rationales concise (single short sentence).\n"
                        "3) Do not include markdown fences or extra text."
                    ),
                },
            ],
            "temperature": self.temperature,
            "top_p": self.top_p,
            "seed": self.seed,
            "max_tokens": 4000,
        }

        response_text = ""
        raw_content: Any = None

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            response_text = response.text

            try:
                data = response.json()
            except ValueError as exc:
                print("OpenRouter response body is not valid JSON.")
                print("Prompt sent to LLM:")
                print(prompt)
                print("LLM output received:")
                print(response_text)
                raise RuntimeError("OpenRouter returned a non-JSON response body") from exc

            choices = data.get("choices")
            if not isinstance(choices, list) or not choices:
                print("OpenRouter response missing choices.")
                print("Prompt sent to LLM:")
                print(prompt)
                print("LLM output received:")
                print(response_text)
                raise RuntimeError("OpenRouter returned no choices")

            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if not isinstance(message, dict):
                print("OpenRouter response missing message payload.")
                print("Prompt sent to LLM:")
                print(prompt)
                print("LLM output received:")
                print(response_text)
                raise RuntimeError("OpenRouter response missing message payload")

            raw_content = message.get("content")
            try:
                return self._parse_json_payload(raw_content)
            except json.JSONDecodeError as exc:
                print("Failed to parse LLM JSON payload.")
                print("Prompt sent to LLM:")
                print(prompt)
                print("LLM output received:")
                print(self._coerce_content(raw_content))
                raise RuntimeError(f"Failed to parse LLM response: {exc}") from exc

        except requests.exceptions.RequestException as e:
            print("OpenRouter API call failed.")
            print("Prompt sent to LLM:")
            print(prompt)
            print("LLM output received:")
            if getattr(e, "response", None) is not None:
                print(e.response.text)
            elif response_text:
                print(response_text)
            else:
                print(None)
            raise RuntimeError(f"OpenRouter API error: {e}") from e
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            print("Unexpected LLM parsing error.")
            print("Prompt sent to LLM:")
            print(prompt)
            print("LLM output received:")
            if raw_content is not None:
                print(self._coerce_content(raw_content))
            elif response_text:
                print(response_text)
            else:
                print(None)
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
