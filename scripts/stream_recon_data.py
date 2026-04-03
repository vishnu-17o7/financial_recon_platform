'''
Command to run the script with optional month-year argument (e.g., "feb-2026" or "2-2026"):
    python stream_recon_data.py [month-year]
This script simulates streaming financial transaction data for reconciliation purposes. It generates two CSV files:
1. ledger_stream.csv: Represents the general ledger transactions.
2. bank_statement_stream.csv: Represents the bank statement transactions.

To generate current month data, simply run:
    python stream_recon_data.py
'''

from __future__ import annotations

import calendar
import csv
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd


LEDGER_COLUMNS = [
    "transaction_date",
    "value_date",
    "debit_amount",
    "credit_amount",
    "transaction_type",
    "narrative",
    "running_bal",
    "purpose_of_payment",
    "customer_ref_id",
    "bank_ref",
    "channel_ref",
]


BANK_COLUMNS = [
    "account_name",
    "account_number",
    "bank_name",
    "currency",
    "location",
    "bic",
    "iban",
    "account_status",
    "account_type",
    "closing_ledger_balance",
    "closing_ledger_brought_forward_from",
    "closing_available_balance",
    "closing_available_brought_forward_from",
    "current_ledger_balance",
    "current_ledger_as_at",
    "current_available_balance",
    "current_available_as_at",
    "bank_reference",
    "narrative",
    "customer_reference",
    "TRN_type",
    "value_date",
    "credit_amount",
    "debit_amount",
    "balance",
    "time",
    "post_date",
]


TWOPLACES = Decimal("0.01")


def d2(value: float | Decimal) -> Decimal:
    """Round to 2 decimal places using financial rounding."""
    if isinstance(value, Decimal):
        return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def fmt_amt(value: Decimal) -> str:
    return f"{value:.2f}"


def append_rows_safe(file_path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    """Append rows with flush+fsync so readers can consume continuously."""
    if not rows:
        return

    with file_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writerows(rows)
        f.flush()
        os.fsync(f.fileno())


def initialize_csv(file_path: Path, fieldnames: list[str]) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if file_path.exists() and file_path.stat().st_size > 0:
        return

    with file_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        f.flush()
        os.fsync(f.fileno())


@dataclass
class StreamStats:
    loops: int = 0
    gl_rows: int = 0
    bank_rows: int = 0
    omitted_in_bank: int = 0
    timing_difference_rows: int = 0
    human_error_rows: int = 0
    duplicate_bank_rows: int = 0


class ReconciliationStreamer:
    def __init__(self, output_dir: str = "data", target_date: datetime | None = None) -> None:
        self.output_dir = Path(output_dir)
        self.ledger_file = self.output_dir / "ledger_stream.csv"
        self.bank_file = self.output_dir / "bank_statement_stream.csv"

        # If target_date is provided, we generate data for that month/year.
        # Otherwise, we use the current date.
        self._target_date = target_date

        self.rng = np.random.default_rng()

        self.gl_balance = d2(100000.00)
        self.bank_balance = d2(100000.00)

        self.ledger_to_bank_probability = 0.85
        self.bank_only_probability = 0.15
        self.human_error_probability = 0.10
        self.duplicate_post_probability = 0.03

        # Fast backfill mode can generate a full monthly dataset quickly.
        self.fast_backfill = True
        self.gl_batch_min = 50
        self.gl_batch_max = 300
        self.sleep_min_seconds = 0.0
        self.sleep_max_seconds = 0.0
        self.ts_step_min_seconds = 900
        self.ts_step_max_seconds = 3600

        self.stats = StreamStats()

        month_start, _ = self._current_month_bounds()
        self.ledger_ts_cursor = month_start - timedelta(seconds=1)
        self.bank_ts_cursor = month_start - timedelta(seconds=1)
        self.bank_value_date_cursor = month_start.date()
        self.bank_post_date_cursor = month_start.date()

        initialize_csv(self.ledger_file, LEDGER_COLUMNS)
        initialize_csv(self.bank_file, BANK_COLUMNS)

        # Lightweight schema validation to ensure exact header order in output files.
        self._validate_headers_with_pandas()

    def _validate_headers_with_pandas(self) -> None:
        ledger_df = pd.read_csv(self.ledger_file, nrows=0)
        bank_df = pd.read_csv(self.bank_file, nrows=0)

        if list(ledger_df.columns) != LEDGER_COLUMNS:
            raise ValueError("Ledger CSV columns do not match required schema.")
        if list(bank_df.columns) != BANK_COLUMNS:
            raise ValueError("Bank statement CSV columns do not match required schema.")

    def _now(self) -> datetime:
        if self._target_date is not None:
            return self._target_date
        return datetime.now()

    def _current_month_bounds(self) -> tuple[datetime, datetime]:
        now = self._now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_last_day = calendar.monthrange(now.year, now.month)[1]
        month_end = now.replace(day=month_last_day, hour=23, minute=59, second=59, microsecond=0)
        return month_start, min(month_end, now)

    def _random_current_month_ts(self) -> datetime:
        month_start, month_end = self._current_month_bounds()
        total_seconds = int((month_end - month_start).total_seconds())
        if total_seconds <= 0:
            return month_end
        offset_seconds = int(self.rng.integers(0, total_seconds + 1))
        return month_start + timedelta(seconds=offset_seconds)

    def _next_ordered_month_ts(
        self,
        cursor_attr: str,
        min_step_seconds: int = 10,
        max_step_seconds: int = 600,
    ) -> datetime:
        month_start, month_end = self._current_month_bounds()
        cursor_value = getattr(self, cursor_attr, month_start - timedelta(seconds=1))
        if cursor_value < month_start:
            cursor_value = month_start - timedelta(seconds=1)

        if cursor_value >= month_end:
            setattr(self, cursor_attr, month_end)
            return month_end

        step = int(self.rng.integers(min_step_seconds, max_step_seconds + 1))
        next_value = min(cursor_value + timedelta(seconds=step), month_end)
        setattr(self, cursor_attr, next_value)
        return next_value

    def _clamp_date_to_current_month(self, value) -> Any:
        month_start, month_end = self._current_month_bounds()
        start_date = month_start.date()
        end_date = month_end.date()
        if value < start_date:
            return start_date
        if value > end_date:
            return end_date
        return value

    def _enforce_bank_date_order(self, bank_row: dict[str, Any]) -> dict[str, Any]:
        value_date = datetime.strptime(str(bank_row["value_date"]), "%Y-%m-%d").date()
        post_date = datetime.strptime(str(bank_row["post_date"]), "%Y-%m-%d").date()

        value_date = self._clamp_date_to_current_month(value_date)
        post_date = self._clamp_date_to_current_month(post_date)

        value_date = max(value_date, self.bank_value_date_cursor)
        post_date = max(post_date, value_date, self.bank_post_date_cursor)

        self.bank_value_date_cursor = value_date
        self.bank_post_date_cursor = post_date

        bank_row["value_date"] = value_date.isoformat()
        bank_row["post_date"] = post_date.isoformat()
        return bank_row

    def _gl_transaction_template(self, txn_ts: datetime) -> tuple[dict[str, Any], Decimal]:
        ledger_txn_id = f"GL-{uuid4().hex[:12].upper()}"
        value_date = txn_ts.date()
        txn_type = self.rng.choice(["PAYMENT", "RECEIPT", "TRANSFER", "CHARGEBACK"])

        # Choose direction and amount, then keep exactly one of debit/credit non-zero.
        is_credit = bool(self.rng.random() < 0.52)
        amount = d2(self.rng.uniform(120.0, 28000.0))

        debit_amount = d2(0.0)
        credit_amount = d2(0.0)
        if is_credit:
            credit_amount = amount
            self.gl_balance = d2(self.gl_balance + amount)
        else:
            debit_amount = amount
            self.gl_balance = d2(self.gl_balance - amount)

        narrative_root = self.rng.choice(
            [
                "Invoice settlement",
                "Vendor payout",
                "Customer collection",
                "UPI transfer",
                "NEFT transfer",
            ]
        )

        customer_ref = f"CUST-{uuid4().hex[:8].upper()}"
        bank_ref = f"BR-{uuid4().hex[:10].upper()}"
        channel_ref = self.rng.choice(["MOBILE", "NETBANKING", "RTGS", "BRANCH"])

        ledger_row = {
            "transaction_date": txn_ts.strftime("%Y-%m-%d %H:%M:%S"),
            "value_date": value_date.isoformat(),
            "debit_amount": fmt_amt(debit_amount),
            "credit_amount": fmt_amt(credit_amount),
            "transaction_type": str(txn_type),
            "narrative": f"{ledger_txn_id} {narrative_root}",
            "running_bal": fmt_amt(self.gl_balance),
            "purpose_of_payment": str(self.rng.choice(["SUPPLIER", "SALARY", "SALES", "REFUND"])),
            "customer_ref_id": customer_ref,
            "bank_ref": bank_ref,
            "channel_ref": str(channel_ref),
        }

        signed_amount = amount if is_credit else d2(-amount)
        return ledger_row, signed_amount

    def _signed_amount_from_bank_row(self, bank_row: dict[str, Any]) -> Decimal:
        credit = d2(Decimal(str(bank_row["credit_amount"])))
        debit = d2(Decimal(str(bank_row["debit_amount"])))
        return d2(credit - debit)

    def _refresh_bank_balance_fields(self, bank_row: dict[str, Any], txn_ts: datetime) -> None:
        balance_text = fmt_amt(self.bank_balance)
        as_at = txn_ts.strftime("%Y-%m-%d %H:%M:%S")
        bank_row["closing_ledger_balance"] = balance_text
        bank_row["closing_available_balance"] = balance_text
        bank_row["current_ledger_balance"] = balance_text
        bank_row["current_available_balance"] = balance_text
        bank_row["current_ledger_as_at"] = as_at
        bank_row["current_available_as_at"] = as_at
        bank_row["balance"] = balance_text
        bank_row["time"] = txn_ts.strftime("%H:%M:%S")

    def _apply_human_error(self, bank_row: dict[str, Any], txn_ts: datetime) -> tuple[dict[str, Any], str]:
        if self.rng.random() >= self.human_error_probability:
            return bank_row, "NONE"

        old_signed = self._signed_amount_from_bank_row(bank_row)
        error_type = str(
            self.rng.choice(["AMOUNT_TYPO", "POLARITY_REVERSAL", "DATE_POSTING_ERROR", "REFERENCE_DROP"])
        )

        if error_type == "AMOUNT_TYPO":
            drift = d2(self.rng.uniform(1.00, 250.00))
            if d2(Decimal(str(bank_row["credit_amount"]))) > d2(0):
                new_credit = d2(Decimal(str(bank_row["credit_amount"])) + drift)
                bank_row["credit_amount"] = fmt_amt(new_credit)
            else:
                new_debit = d2(Decimal(str(bank_row["debit_amount"])) + drift)
                bank_row["debit_amount"] = fmt_amt(new_debit)
            bank_row["narrative"] = f"{bank_row['narrative']} AMOUNT_TYPO"

        elif error_type == "POLARITY_REVERSAL":
            credit_text = bank_row["credit_amount"]
            bank_row["credit_amount"] = bank_row["debit_amount"]
            bank_row["debit_amount"] = credit_text
            bank_row["narrative"] = f"{bank_row['narrative']} POLARITY_REVERSAL"

        elif error_type == "DATE_POSTING_ERROR":
            month_start, month_end = self._current_month_bounds()
            random_day = int(self.rng.integers(month_start.day, month_end.day + 1))
            forced_value_date = month_start.replace(day=random_day).date()
            forced_post_date = self._clamp_date_to_current_month(
                forced_value_date + timedelta(days=int(self.rng.integers(0, 3)))
            )
            bank_row["value_date"] = forced_value_date.isoformat()
            bank_row["post_date"] = forced_post_date.isoformat()
            bank_row["narrative"] = f"{bank_row['narrative']} DATE_POSTING_ERROR"

        else:
            bank_row["customer_reference"] = ""
            bank_row["bank_reference"] = ""
            bank_row["narrative"] = f"{bank_row['narrative']} REFERENCE_DROP"

        new_signed = self._signed_amount_from_bank_row(bank_row)
        self.bank_balance = d2(self.bank_balance + (new_signed - old_signed))
        bank_row = self._enforce_bank_date_order(bank_row)
        self._refresh_bank_balance_fields(bank_row, txn_ts)
        return bank_row, error_type

    def _build_duplicate_posting(self, bank_row: dict[str, Any], txn_ts: datetime) -> dict[str, Any]:
        duplicate_row = dict(bank_row)
        original_ref = str(bank_row["bank_reference"]) or f"BNK-{uuid4().hex[:12].upper()}"
        duplicate_row["bank_reference"] = f"{original_ref}-DUP"
        duplicate_row["narrative"] = f"{bank_row['narrative']} DUPLICATE_POSTING"

        signed_amount = self._signed_amount_from_bank_row(duplicate_row)
        self.bank_balance = d2(self.bank_balance + signed_amount)
        duplicate_row = self._enforce_bank_date_order(duplicate_row)
        self._refresh_bank_balance_fields(duplicate_row, txn_ts)
        return duplicate_row

    def _build_bank_row_from_ledger(
        self,
        ledger_row: dict[str, Any],
        signed_amount: Decimal,
        txn_ts: datetime,
    ) -> tuple[dict[str, Any], str, Decimal]:
        base_value_date = datetime.strptime(ledger_row["value_date"], "%Y-%m-%d").date()
        date_jitter = int(self.rng.integers(-1, 3))
        bank_value_date = base_value_date + timedelta(days=date_jitter)
        bank_value_date = self._clamp_date_to_current_month(bank_value_date)
        post_date = bank_value_date + timedelta(days=int(self.rng.integers(0, 2)))
        post_date = self._clamp_date_to_current_month(post_date)

        # 5% amount discrepancy between Rs 0.01 and Rs 0.50.
        discrepancy = d2(0.0)
        amount_mismatch = bool(self.rng.random() < 0.05)
        if amount_mismatch:
            discrepancy = d2(self.rng.uniform(0.01, 0.50))

        ledger_abs = d2(abs(signed_amount))
        bank_abs = ledger_abs
        if amount_mismatch:
            bank_abs = d2(ledger_abs + discrepancy)

        if signed_amount >= d2(0):
            credit_amount = bank_abs
            debit_amount = d2(0.0)
            self.bank_balance = d2(self.bank_balance + bank_abs)
        else:
            debit_amount = bank_abs
            credit_amount = d2(0.0)
            self.bank_balance = d2(self.bank_balance - bank_abs)

        original_narr = str(ledger_row["narrative"])
        narrative_variant = original_narr
        if self.rng.random() < 0.65:
            narrative_variant = f"{original_narr} BANK"

        drop_customer_ref = bool(self.rng.random() < 0.20)
        customer_reference = "" if drop_customer_ref else str(ledger_row["customer_ref_id"])

        bank_txn_id = f"BNK-{uuid4().hex[:12].upper()}"

        bank_row = {
            "account_name": "Demo Company Pvt Ltd",
            "account_number": "1234567890",
            "bank_name": "Demo Bank Ltd",
            "currency": "INR",
            "location": "Coimbatore",
            "bic": "DEMOINCCXXX",
            "iban": "IN00DEMO1234567890",
            "account_status": "ACTIVE",
            "account_type": "CURRENT",
            "closing_ledger_balance": fmt_amt(self.bank_balance),
            "closing_ledger_brought_forward_from": (txn_ts - timedelta(days=1)).strftime("%Y-%m-%d"),
            "closing_available_balance": fmt_amt(self.bank_balance),
            "closing_available_brought_forward_from": (txn_ts - timedelta(days=1)).strftime("%Y-%m-%d"),
            "current_ledger_balance": fmt_amt(self.bank_balance),
            "current_ledger_as_at": txn_ts.strftime("%Y-%m-%d %H:%M:%S"),
            "current_available_balance": fmt_amt(self.bank_balance),
            "current_available_as_at": txn_ts.strftime("%Y-%m-%d %H:%M:%S"),
            "bank_reference": bank_txn_id,
            "narrative": narrative_variant,
            "customer_reference": customer_reference,
            "TRN_type": ledger_row["transaction_type"],
            "value_date": bank_value_date.isoformat(),
            "credit_amount": fmt_amt(credit_amount),
            "debit_amount": fmt_amt(debit_amount),
            "balance": fmt_amt(self.bank_balance),
            "time": txn_ts.strftime("%H:%M:%S"),
            "post_date": post_date.isoformat(),
        }
        bank_row = self._enforce_bank_date_order(bank_row)

        status = "EXACT_MATCH"
        if amount_mismatch:
            status = "AMOUNT_MISMATCH"
        elif date_jitter != 0:
            status = "DATE_MISMATCH"

        return bank_row, status, bank_abs

    def _build_bank_only_fee(self, txn_ts: datetime) -> tuple[dict[str, Any], Decimal]:
        fee_type = str(
            self.rng.choice(["Monthly Account Fee", "Sweep Interest", "Overdraft Charge", "Card Network Charge"])
        )
        fee_credit = bool(fee_type == "Sweep Interest")
        amount = d2(self.rng.uniform(5.0, 350.0))

        credit_amount = d2(0.0)
        debit_amount = d2(0.0)
        signed_amount = d2(0.0)
        if fee_credit:
            credit_amount = amount
            signed_amount = amount
            self.bank_balance = d2(self.bank_balance + amount)
        else:
            debit_amount = amount
            signed_amount = d2(-amount)
            self.bank_balance = d2(self.bank_balance - amount)

        value_date = txn_ts.date() + timedelta(days=int(self.rng.integers(0, 2)))
        value_date = self._clamp_date_to_current_month(value_date)
        post_date = value_date + timedelta(days=int(self.rng.integers(0, 2)))
        post_date = self._clamp_date_to_current_month(post_date)

        bank_txn_id = f"BNK-{uuid4().hex[:12].upper()}"

        bank_row = {
            "account_name": "Demo Company Pvt Ltd",
            "account_number": "1234567890",
            "bank_name": "Demo Bank Ltd",
            "currency": "INR",
            "location": "Coimbatore",
            "bic": "DEMOINCCXXX",
            "iban": "IN00DEMO1234567890",
            "account_status": "ACTIVE",
            "account_type": "CURRENT",
            "closing_ledger_balance": fmt_amt(self.bank_balance),
            "closing_ledger_brought_forward_from": (txn_ts - timedelta(days=1)).strftime("%Y-%m-%d"),
            "closing_available_balance": fmt_amt(self.bank_balance),
            "closing_available_brought_forward_from": (txn_ts - timedelta(days=1)).strftime("%Y-%m-%d"),
            "current_ledger_balance": fmt_amt(self.bank_balance),
            "current_ledger_as_at": txn_ts.strftime("%Y-%m-%d %H:%M:%S"),
            "current_available_balance": fmt_amt(self.bank_balance),
            "current_available_as_at": txn_ts.strftime("%Y-%m-%d %H:%M:%S"),
            "bank_reference": bank_txn_id,
            "narrative": fee_type,
            "customer_reference": "",
            "TRN_type": "BANK_ONLY",
            "value_date": value_date.isoformat(),
            "credit_amount": fmt_amt(credit_amount),
            "debit_amount": fmt_amt(debit_amount),
            "balance": fmt_amt(self.bank_balance),
            "time": txn_ts.strftime("%H:%M:%S"),
            "post_date": post_date.isoformat(),
        }
        bank_row = self._enforce_bank_date_order(bank_row)

        return bank_row, signed_amount

    def _print_summary(self, elapsed: timedelta) -> None:
        print("\nGeneration summary:")
        print(f"Elapsed: {elapsed}")
        print(f"Loops: {self.stats.loops}")
        print(f"Total GL rows: {self.stats.gl_rows}")
        print(f"Total Bank rows: {self.stats.bank_rows}")
        print(f"Omissions (GL not in Bank): {self.stats.omitted_in_bank}")
        print(f"Timing differences: {self.stats.timing_difference_rows}")
        print(f"Human-error rows: {self.stats.human_error_rows}")
        print(f"Duplicate postings: {self.stats.duplicate_bank_rows}")
        print(f"Final GL balance: Rs {self.gl_balance:,.2f}")
        print(f"Final Bank balance: Rs {self.bank_balance:,.2f}")
        print(f"Final drift: Rs {abs(self.gl_balance - self.bank_balance):,.2f}")

    def run(self) -> None:
        start_ts = self._now()
        month_label = start_ts.strftime("%B %Y")
        print("Streaming reconciliation simulator started.")
        print(f"Target month: {month_label}")
        print(f"Ledger output: {self.ledger_file}")
        print(f"Bank output:   {self.bank_file}")
        if self.fast_backfill:
            print("Mode: FAST_BACKFILL (finite run for full current-month coverage)")
        else:
            print("Mode: STREAMING (continuous)")

        try:
            while True:
                loop_ts = self._now()
                self.stats.loops += 1

                # End condition for finite month backfill mode.
                if self.fast_backfill:
                    _, month_end = self._current_month_bounds()
                    if self.ledger_ts_cursor >= month_end and self.bank_ts_cursor >= month_end:
                        print("Reached month end for both ledgers and bank stream. Stopping.")
                        break

                gl_batch_count = int(self.rng.integers(self.gl_batch_min, self.gl_batch_max + 1))

                ledger_rows: list[dict[str, Any]] = []
                bank_rows: list[dict[str, Any]] = []

                for _ in range(gl_batch_count):
                    event_ts = self._next_ordered_month_ts(
                        "ledger_ts_cursor",
                        min_step_seconds=self.ts_step_min_seconds,
                        max_step_seconds=self.ts_step_max_seconds,
                    )
                    ledger_row, signed_amount = self._gl_transaction_template(event_ts)
                    ledger_rows.append(ledger_row)

                    # 85% of ledger transactions produce a bank entry; remaining are omissions in bank.
                    if self.rng.random() < self.ledger_to_bank_probability:
                        bank_event_ts = self._next_ordered_month_ts(
                            "bank_ts_cursor",
                            min_step_seconds=self.ts_step_min_seconds,
                            max_step_seconds=self.ts_step_max_seconds,
                        )
                        bank_row, status, _ = self._build_bank_row_from_ledger(ledger_row, signed_amount, bank_event_ts)
                        if status == "DATE_MISMATCH":
                            self.stats.timing_difference_rows += 1

                        bank_row, error_type = self._apply_human_error(bank_row, bank_event_ts)
                        if error_type != "NONE":
                            self.stats.human_error_rows += 1

                        bank_rows.append(bank_row)

                        if self.rng.random() < self.duplicate_post_probability:
                            duplicate_event_ts = self._next_ordered_month_ts(
                                "bank_ts_cursor",
                                min_step_seconds=self.ts_step_min_seconds,
                                max_step_seconds=self.ts_step_max_seconds,
                            )
                            duplicate_row = self._build_duplicate_posting(bank_row, duplicate_event_ts)
                            bank_rows.append(duplicate_row)
                            self.stats.human_error_rows += 1
                            self.stats.duplicate_bank_rows += 1
                    else:
                        self.stats.omitted_in_bank += 1

                # Approx. 15% bank-only rows against this cycle's GL count.
                bank_only_count = int(self.rng.binomial(gl_batch_count, self.bank_only_probability))
                for _ in range(bank_only_count):
                    event_ts = self._next_ordered_month_ts(
                        "bank_ts_cursor",
                        min_step_seconds=self.ts_step_min_seconds,
                        max_step_seconds=self.ts_step_max_seconds,
                    )
                    bank_row, _ = self._build_bank_only_fee(event_ts)
                    bank_row, error_type = self._apply_human_error(bank_row, event_ts)
                    if error_type != "NONE":
                        self.stats.human_error_rows += 1
                    bank_rows.append(bank_row)

                append_rows_safe(self.ledger_file, LEDGER_COLUMNS, ledger_rows)
                append_rows_safe(self.bank_file, BANK_COLUMNS, bank_rows)

                self.stats.gl_rows += len(ledger_rows)
                self.stats.bank_rows += len(bank_rows)

                drift = d2(self.gl_balance - self.bank_balance)
                drift_abs = abs(drift)
                now_label = loop_ts.strftime("%H:%M:%S")
                print(
                    f"[{now_label}] Wrote {len(ledger_rows)} GL & {len(bank_rows)} Bank txns. "
                    f"GL Bal: Rs {self.gl_balance:,.2f} | Bank Bal: Rs {self.bank_balance:,.2f}. "
                    f"Drift: Rs {drift_abs:,.2f}"
                )

                sleep_seconds = float(self.rng.uniform(self.sleep_min_seconds, self.sleep_max_seconds))
                time.sleep(max(0.0, sleep_seconds))

            elapsed = self._now() - start_ts
            self._print_summary(elapsed)

        except KeyboardInterrupt:
            elapsed = self._now() - start_ts
            print("\nStopped by user.")
            self._print_summary(elapsed)


if __name__ == "__main__":
    import sys
    
    target_date = None
    if len(sys.argv) > 1:
        month_year = sys.argv[1]  # Format: "feb-2026" or "2-2026" (month-year)
        try:
            parts = month_year.lower().split('-')
            if len(parts) != 2:
                raise ValueError("Use format: month-year (e.g., 'feb-2026' or '2-2026')")
            
            month_str, year_str = parts
            year = int(year_str)
            
            # Handle month as name or number
            if month_str.isdigit():
                month = int(month_str)
            else:
                # Map month name to number
                month_map = {
                    'jan': 1, 'january': 1,
                    'feb': 2, 'february': 2,
                    'mar': 3, 'march': 3,
                    'apr': 4, 'april': 4,
                    'may': 5,
                    'jun': 6, 'june': 6,
                    'jul': 7, 'july': 7,
                    'aug': 8, 'august': 8,
                    'sep': 9, 'september': 9,
                    'oct': 10, 'october': 10,
                    'nov': 11, 'november': 11,
                    'dec': 12, 'december': 12,
                }
                month = month_map.get(month_str.lower())
                if month is None:
                    raise ValueError(f"Unknown month: {month_str}")
            
            # Set target_date to the last day of the target month
            last_day = calendar.monthrange(year, month)[1]
            target_date = datetime(year, month, last_day, 23, 59, 59)
            print(f"Generating data for {target_date.strftime('%B %Y')}...")
        except Exception as e:
            print(f"Error parsing month-year: {e}")
            print("Usage: python stream_recon_data.py [month-year]")
            print("Examples: python stream_recon_data.py feb-2026")
            print("          python stream_recon_data.py 2-2026")
            sys.exit(1)
    
    streamer = ReconciliationStreamer(output_dir="sample_data", target_date=target_date)
    streamer.run()