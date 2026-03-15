from decimal import Decimal

from sqlalchemy.orm import Session

from app.llm.interfaces import EmbeddingClient, LLMClient
from app.matching.engine import HybridMatchingEngine, MatchingStrategy
from app.matching.types import CandidateScore, TransactionFeature
from app.models.enums import ScenarioType


SCENARIO_PROFILES: dict[ScenarioType, dict[str, Decimal | int]] = {
    ScenarioType.VENDOR_AP: {"amount_tolerance": Decimal("5.00"), "date_window_days": 7},
    ScenarioType.CREDIT_CARD_EXPENSE: {"amount_tolerance": Decimal("3.00"), "date_window_days": 5},
    ScenarioType.PAYROLL: {"amount_tolerance": Decimal("1.00"), "date_window_days": 2},
    ScenarioType.TAX: {"amount_tolerance": Decimal("10.00"), "date_window_days": 10},
    ScenarioType.INTERCOMPANY: {"amount_tolerance": Decimal("20.00"), "date_window_days": 15},
    ScenarioType.SUBLEDGER_GL: {"amount_tolerance": Decimal("2.00"), "date_window_days": 3},
    ScenarioType.CASH_BALANCE: {"amount_tolerance": Decimal("50.00"), "date_window_days": 2},
}


class GenericProfileMatchingStrategy(MatchingStrategy):
    """Config-driven strategy used for day-one support of additional scenarios."""

    def __init__(self, scenario_type: ScenarioType):
        cfg = SCENARIO_PROFILES[scenario_type]
        self.engine = HybridMatchingEngine(
            amount_tolerance=cfg["amount_tolerance"], date_window_days=int(cfg["date_window_days"])
        )

    def match(
        self,
        db: Session,
        side_a: list[TransactionFeature],
        side_b: list[TransactionFeature],
        llm_client: LLMClient,
        embedding_client: EmbeddingClient,
    ) -> tuple[list[CandidateScore], list[str]]:
        used_b: set[str] = set()
        matched: list[CandidateScore] = []
        unmatched: list[str] = []
        tx_map = {t.id: t for t in side_a + side_b}

        for a in side_a:
            pool = [b for b in self.engine.candidate_pool(a, side_b) if b.id not in used_b]
            if not pool:
                unmatched.append(a.id)
                continue

            a_emb = self.engine.ensure_embedding(
                db, a.id, self.engine.build_embedding_text(a), "mock-embedding", embedding_client
            )
            scored: list[CandidateScore] = []
            for b in pool:
                b_emb = self.engine.ensure_embedding(
                    db, b.id, self.engine.build_embedding_text(b), "mock-embedding", embedding_client
                )
                scored.append(self.engine.score_candidate(a, b, self.engine.cosine_similarity(a_emb, b_emb)))

            best = self.engine.tie_break_with_llm(a, scored, tx_map, llm_client)
            matched.append(best)
            used_b.add(best.transaction_b_id)

        return matched, unmatched
