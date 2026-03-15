import pandas as pd

from app.ingestion.base import BaseParser, ParsedRecord


class GLExportCSVParser(BaseParser):
    source_type = "gl_export"
    source_system = "erp_gl"

    def parse(self, file_path: str) -> list[ParsedRecord]:
        df = pd.read_excel(file_path) if file_path.endswith((".xlsx", ".xls")) else pd.read_csv(file_path)
        records: list[ParsedRecord] = []
        for idx, row in df.iterrows():
            records.append(
                ParsedRecord(
                    row_number=idx + 1,
                    payload={
                        "posting_date": row.get("posting_date"),
                        "narration": row.get("narration"),
                        "debit": row.get("debit", 0),
                        "credit": row.get("credit", 0),
                        "currency": row.get("currency", "INR"),
                        "voucher_no": row.get("voucher_no"),
                        "account_code": row.get("account_code"),
                        "counterparty": row.get("counterparty"),
                    },
                )
            )
        return records
