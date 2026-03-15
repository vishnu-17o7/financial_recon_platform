from pathlib import Path

from sqlalchemy.orm import Session

from app.ingestion.base import BaseParser
from app.ingestion.parsers.bank_csv_parser import GenericBankCSVParser
from app.ingestion.parsers.gl_csv_parser import GLExportCSVParser
from app.ingestion.parsers.psp_csv_parser import PSPPaymentsCSVParser
from app.llm.interfaces import LLMClient
from app.models.entities import TransactionNormalized, TransactionRaw
from app.models.enums import ScenarioType
from app.services.normalization_service import normalize_record


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, BaseParser] = {
            "bank_csv": GenericBankCSVParser(),
            "gl_csv": GLExportCSVParser(),
            "psp_csv": PSPPaymentsCSVParser(),
        }

    def get(self, parser_key: str) -> BaseParser:
        if parser_key not in self._parsers:
            raise ValueError(f"unsupported parser '{parser_key}'")
        return self._parsers[parser_key]


class NormalizationPipelineService:
    def __init__(self, llm_client: LLMClient | None = None):
        self.llm_client = llm_client

    @staticmethod
    def _infer_side(raw_txn: TransactionRaw) -> str:
        if raw_txn.source_type in {"bank_statement", "psp_payments", "credit_card_statement", "payroll_bank"}:
            return "A"
        return "B"

    def normalize_batch(self, db: Session, ingestion_batch_id: str) -> int:
        raw_records = (
            db.query(TransactionRaw)
            .filter(TransactionRaw.ingestion_batch_id == ingestion_batch_id)
            .order_by(TransactionRaw.row_number.asc())
            .all()
        )
        count = 0
        for raw in raw_records:
            norm = normalize_record(
                raw=raw.raw_payload,
                scenario_type=raw.scenario_type,
                source_type=raw.source_type,
                source_system=raw.source_system,
                raw_transaction_id=raw.id,
                side=self._infer_side(raw),
                llm_client=self.llm_client,
            )
            db.add(TransactionNormalized(**norm.model_dump()))
            count += 1
        db.commit()
        return count


def save_upload(file_name: str, content: bytes) -> str:
    upload_dir = Path("tmp_uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / file_name
    path.write_bytes(content)
    return str(path)


def scenario_from_text(value: str) -> ScenarioType:
    return ScenarioType(value)
