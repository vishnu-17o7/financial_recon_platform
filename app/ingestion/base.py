from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ParsedRecord:
    row_number: int
    payload: dict[str, Any]


class BaseParser(ABC):
    source_type: str
    source_system: str

    @property
    def source_metadata(self) -> dict[str, str]:
        return {
            "source_type": self.source_type,
            "source_system": self.source_system,
        }

    @abstractmethod
    def parse(self, file_path: str) -> list[ParsedRecord]:
        raise NotImplementedError
