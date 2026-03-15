import pandas as pd

from app.ingestion.base import BaseParser, ParsedRecord


class GenericBankCSVParser(BaseParser):
    source_type = "bank_statement"
    source_system = "generic_bank"

    def parse(self, file_path: str) -> list[ParsedRecord]:
        df = pd.read_excel(file_path) if file_path.endswith((".xlsx", ".xls")) else pd.read_csv(file_path)
        records: list[ParsedRecord] = []
        for idx, row in df.iterrows():
            records.append(
                ParsedRecord(
                    row_number=idx + 1,
                    payload={
                        "txn_date": row.get("txn_date"),
                        "value_date": row.get("value_date"),
                        "description": row.get("description"),
                        "amount": row.get("amount"),
                        "currency": row.get("currency", "INR"),
                        "reference": row.get("reference"),
                        "counterparty": row.get("counterparty"),
                        "dr_cr": row.get("dr_cr"),
                        "account_code": row.get("account_code"),
                    },
                )
            )
        return records
