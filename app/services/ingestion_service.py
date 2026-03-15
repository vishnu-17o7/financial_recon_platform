import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.ingestion.base import BaseParser
from app.models.entities import TransactionRaw
from app.models.enums import ScenarioType


class IngestionService:
    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(k): IngestionService._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [IngestionService._json_safe(v) for v in value]

        if value is None:
            return None

        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return None
            return value

        if isinstance(value, (datetime, date)):
            return value.isoformat()

        if isinstance(value, Decimal):
            return float(value)

        if hasattr(value, "item") and callable(getattr(value, "item")):
            try:
                return IngestionService._json_safe(value.item())
            except Exception:
                pass

        if value.__class__.__name__ in {"NAType", "NaTType"}:
            return None

        text = str(value)
        if text in {"NaN", "nan", "<NA>", "NaT"}:
            return None

        return value

    def ingest_file(
        self,
        db: Session,
        parser: BaseParser,
        file_path: str,
        scenario_type: ScenarioType,
    ) -> str:
        batch_id = str(uuid4())
        parsed = parser.parse(file_path)
        for rec in parsed:
            db.add(
                TransactionRaw(
                    ingestion_batch_id=batch_id,
                    source_type=parser.source_type,
                    source_system=parser.source_system,
                    scenario_type=scenario_type,
                    file_name=file_path.split("/")[-1],
                    row_number=rec.row_number,
                    raw_payload=self._json_safe(rec.payload),
                    parser_name=parser.__class__.__name__,
                )
            )
        db.commit()
        return batch_id
