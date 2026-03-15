from decimal import Decimal
from itertools import combinations

from sqlalchemy.orm import Session

from app.llm.interfaces import EmbeddingClient, LLMClient
from app.matching.engine import HybridMatchingEngine, MatchingStrategy
from app.matching.types import CandidateScore, TransactionFeature


class CustomerARMatchingStrategy(MatchingStrategy):
    """Customer payment <-> AR invoices, including 1-to-many invoice settlement."""

    def __init__(self, engine: HybridMatchingEngine | None = None):
        self.engine = engine or HybridMatchingEngine(amount_tolerance=Decimal("5.00"), date_window_days=7)

    @staticmethod
    def scenario_filter(a: TransactionFeature, b: TransactionFeature) -> bool:
        if a.counterparty and b.counterparty and a.counterparty != b.counterparty:
            return False
        return True

    def _try_one_to_many(
        self,
        a: TransactionFeature,
        pool: list[TransactionFeature],
    ) -> list[TransactionFeature]:
        small_pool = pool[:6]
        for r in range(2, 4):
            for combo in combinations(small_pool, r):
                total = sum((x.amount for x in combo), Decimal("0"))
                if abs(total - a.amount) <= self.engine.amount_tolerance:
                    return list(combo)
        return []

    def match(
        self,
        db: Session,
        side_a: list[TransactionFeature],
        side_b: list[TransactionFeature],
        llm_client: LLMClient,
        embedding_client: EmbeddingClient,
    ) -> tuple[list[CandidateScore], list[str]]:
        matched: list[CandidateScore] = []
        used_b: set[str] = set()
        unmatched_a: list[str] = []
        tx_map = {t.id: t for t in side_a + side_b}

        for a in side_a:
            pool = [c for c in self.engine.candidate_pool(a, side_b, self.scenario_filter) if c.id not in used_b]
            if not pool:
                unmatched_a.append(a.id)
                continue

            combo = self._try_one_to_many(a, pool)
            if combo:
                for c in combo:
                    matched.append(
                        CandidateScore(
                            transaction_a_id=a.id,
                            transaction_b_id=c.id,
                            score=0.9,
                            algorithm="ar_one_to_many",
                            reason="payment amount explained by multiple invoices",
                            amount_delta=abs(a.amount - c.amount),
                            date_delta_days=abs((a.date - c.date).days),
                        )
                    )
                    used_b.add(c.id)
                continue

            a_emb = self.engine.ensure_embedding(
                db, a.id, self.engine.build_embedding_text(a), "mock-embedding", embedding_client
            )
            scores: list[CandidateScore] = []
            for b in pool:
                b_emb = self.engine.ensure_embedding(
                    db, b.id, self.engine.build_embedding_text(b), "mock-embedding", embedding_client
                )
                score = self.engine.score_candidate(a, b, self.engine.cosine_similarity(a_emb, b_emb))
                if a.reference and b.reference and a.reference in b.reference:
                    score.score = min(1.0, score.score + 0.15)
                scores.append(score)

            best = self.engine.tie_break_with_llm(a, scores, tx_map, llm_client)
            matched.append(best)
            used_b.add(best.transaction_b_id)

        return matched, unmatched_a
