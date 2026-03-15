from datetime import date
from decimal import Decimal

from app.matching.engine import HybridMatchingEngine
from app.matching.scoring import amount_score, date_score
from app.matching.types import TransactionFeature


def test_scoring_functions():
    assert amount_score(Decimal("100"), Decimal("100"), Decimal("5")) == 1.0
    assert date_score(date(2025, 1, 1), date(2025, 1, 1), 5) == 1.0


def test_candidate_pool_filters():
    engine = HybridMatchingEngine(amount_tolerance=Decimal("5"), date_window_days=3)
    a = TransactionFeature("a1", "A", date(2025, 2, 1), Decimal("100"), "INR", "x", None, None, None, "bank_gl")
    b1 = TransactionFeature("b1", "B", date(2025, 2, 2), Decimal("101"), "INR", "x", None, None, None, "bank_gl")
    b2 = TransactionFeature("b2", "B", date(2025, 2, 10), Decimal("101"), "INR", "x", None, None, None, "bank_gl")
    pool = engine.candidate_pool(a, [b1, b2])
    assert len(pool) == 1
    assert pool[0].id == "b1"
