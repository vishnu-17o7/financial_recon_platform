import pandas as pd

from app.ingestion.base import BaseParser, ParsedRecord


class PSPPaymentsCSVParser(BaseParser):
    source_type = "psp_payments"
    source_system = "generic_psp"

    def parse(self, file_path: str) -> list[ParsedRecord]:
        df = pd.read_excel(file_path) if file_path.endswith((".xlsx", ".xls")) else pd.read_csv(file_path)
        records: list[ParsedRecord] = []
        for idx, row in df.iterrows():
            records.append(
                ParsedRecord(
                    row_number=idx + 1,
                    payload={
                        "payment_date": row.get("payment_date"),
                        "settlement_date": row.get("settlement_date"),
                        "customer_name": row.get("customer_name"),
                        "invoice_ref": row.get("invoice_ref"),
                        "payment_id": row.get("payment_id"),
                        "amount": row.get("amount"),
                        "currency": row.get("currency", "INR"),
                        "status": row.get("status"),
                    },
                )
            )
        return records
