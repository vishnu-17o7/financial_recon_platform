from enum import Enum


class AccountType(str, Enum):
    BANK = "bank"
    GL = "gl"
    CREDIT_CARD = "credit_card"
    AR = "ar"
    AP = "ap"
    PAYROLL = "payroll"
    TAX = "tax"
    INTERCOMPANY = "intercompany"
    TREASURY = "treasury"


class ScenarioType(str, Enum):
    BANK_GL = "bank_gl"
    CUSTOMER_AR = "customer_ar"
    VENDOR_AP = "vendor_ap"
    CREDIT_CARD_EXPENSE = "credit_card_expense"
    PAYROLL = "payroll"
    TAX = "tax"
    INTERCOMPANY = "intercompany"
    SUBLEDGER_GL = "subledger_gl"
    CASH_BALANCE = "cash_balance"


class Direction(str, Enum):
    IN = "in"
    OUT = "out"


class JobStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ExceptionStatus(str, Enum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"


class MatchType(str, Enum):
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    AGGREGATE = "aggregate"
