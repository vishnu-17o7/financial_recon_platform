import hashlib
from typing import Any

import numpy as np

from app.config.settings import get_settings
from app.llm.interfaces import EmbeddingClient, LLMClient


class MockLLMClient(LLMClient):
    def complete_json(self, prompt: str) -> dict[str, Any]:
        prompt_l = prompt.lower()
        if "tie-break" in prompt_l or "candidate" in prompt_l:
            return {
                "recommended_match_index": 0,
                "suggested_confidence": 0.82,
                "reason": "Top candidate has closest amount/date/reference overlap.",
                "requires_human_review": False,
            }
        if "unreconciled" in prompt_l or "exception" in prompt_l:
            return {
                "explanation": "No candidate satisfied tolerance and date constraints.",
                "actions": [
                    "Post missing entry in counterpart ledger.",
                    "Validate reference mapping and vendor/customer master.",
                ],
            }
        return {
            "normalized_name": "unknown",
            "transaction_type": "other",
            "reference_numbers": [],
        }


class MockEmbeddingClient(EmbeddingClient):
    def __init__(self) -> None:
        self.dim = get_settings().vector_dim

    def embed_text(self, text: str) -> list[float]:
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = np.random.default_rng(seed)
        return rng.normal(0, 1, self.dim).astype(float).tolist()
