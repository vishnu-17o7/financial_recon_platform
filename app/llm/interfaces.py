from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    def complete_json(self, prompt: str) -> dict:
        raise NotImplementedError


class EmbeddingClient(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError
