from datetime import date
from decimal import Decimal


def amount_score(a: Decimal, b: Decimal, tolerance: Decimal) -> float:
    delta = abs(a - b)
    if delta == 0:
        return 1.0
    if delta <= tolerance:
        return max(0.0, 1.0 - float(delta / (tolerance + Decimal("0.01"))))
    return 0.0


def date_score(a: date, b: date, max_window_days: int) -> float:
    delta = abs((a - b).days)
    if delta == 0:
        return 1.0
    if delta <= max_window_days:
        return max(0.0, 1.0 - (delta / max_window_days))
    return 0.0


def ref_bonus(ref_a: str | None, ref_b: str | None) -> float:
    if ref_a and ref_b and ref_a.strip().lower() == ref_b.strip().lower():
        return 0.2
    return 0.0


def weighted_confidence(rule_score: float, embedding_similarity: float | None = None) -> float:
    if embedding_similarity is None:
        return min(1.0, max(0.0, rule_score))
    return min(1.0, max(0.0, 0.7 * rule_score + 0.3 * embedding_similarity))
