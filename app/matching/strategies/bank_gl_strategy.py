from decimal import Decimal

from sqlalchemy.orm import Session

from app.llm.interfaces import EmbeddingClient, LLMClient
from app.matching.engine import HybridMatchingEngine, MatchingStrategy
from app.matching.types import CandidateScore, TransactionFeature


class BankGLMatchingStrategy(MatchingStrategy):
    """Bank <-> GL cash strategy with fee/interest tolerance support."""

    def __init__(self, engine: HybridMatchingEngine | None = None):
        self.engine = engine or HybridMatchingEngine(amount_tolerance=Decimal("10.00"), date_window_days=4)

    @staticmethod
    def scenario_filter(a: TransactionFeature, b: TransactionFeature) -> bool:
        if a.account_id and b.account_id and a.account_id != b.account_id:
            return False
        return True

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

            a_emb = self.engine.ensure_embedding(
                db, a.id, self.engine.build_embedding_text(a), "mock-embedding", embedding_client
            )
            candidate_scores: list[CandidateScore] = []
            for b in pool:
                b_emb = self.engine.ensure_embedding(
                    db, b.id, self.engine.build_embedding_text(b), "mock-embedding", embedding_client
                )
                similarity = self.engine.cosine_similarity(a_emb, b_emb)
                score = self.engine.score_candidate(a, b, similarity)

                if "fee" in (a.description or "") or "interest" in (a.description or ""):
                    score.score = max(score.score, 0.7)
                    score.reason += " + fee/interest heuristic"
                candidate_scores.append(score)

            if not candidate_scores:
                unmatched_a.append(a.id)
                continue

            best = self.engine.tie_break_with_llm(a, candidate_scores, tx_map, llm_client)
            matched.append(best)
            used_b.add(best.transaction_b_id)

        return matched, unmatched_a
