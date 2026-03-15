from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.llm.interfaces import EmbeddingClient, LLMClient
from app.llm.prompt_builders import build_tiebreak_prompt
from app.matching.scoring import amount_score, date_score, ref_bonus, weighted_confidence
from app.matching.types import CandidateScore, TransactionFeature
from app.models.entities import EmbeddingRecord, TransactionNormalized


class MatchingStrategy(ABC):
    @abstractmethod
    def match(
        self,
        db: Session,
        side_a: list[TransactionFeature],
        side_b: list[TransactionFeature],
        llm_client: LLMClient,
        embedding_client: EmbeddingClient,
    ) -> tuple[list[CandidateScore], list[str]]:
        """Returns matched candidate scores and list of unmatched transaction A ids."""


class HybridMatchingEngine:
    def __init__(self, amount_tolerance: Decimal = Decimal("5.00"), date_window_days: int = 5):
        self.amount_tolerance = amount_tolerance
        self.date_window_days = date_window_days

    def build_embedding_text(self, t: TransactionFeature) -> str:
        return (
            f"direction: {t.side}; amount: {t.amount}; currency: {t.currency}; date: {t.date}; "
            f"description: {t.description}; counterparty: {t.counterparty}; ref: {t.reference}"
        )

    def ensure_embedding(
        self,
        db: Session,
        transaction_id: str,
        text: str,
        embedding_model: str,
        embedding_client: EmbeddingClient,
    ) -> list[float]:
        existing = db.query(EmbeddingRecord).filter(EmbeddingRecord.transaction_id == transaction_id).first()
        if existing:
            return existing.vector
        vector = embedding_client.embed_text(text)
        rec = EmbeddingRecord(
            transaction_id=transaction_id,
            embedding_model=embedding_model,
            vector=vector,
            content_hash=str(hash(text)),
        )
        db.add(rec)
        db.flush()
        return vector

    @staticmethod
    def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        na = sum(a * a for a in vec_a) ** 0.5
        nb = sum(b * b for b in vec_b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def candidate_pool(
        self,
        a: TransactionFeature,
        side_b: list[TransactionFeature],
        scenario_filter: Callable[[TransactionFeature, TransactionFeature], bool] | None = None,
    ) -> list[TransactionFeature]:
        candidates = []
        for b in side_b:
            if b.currency != a.currency:
                continue
            if abs(a.amount - b.amount) > self.amount_tolerance:
                continue
            if abs((a.date - b.date).days) > self.date_window_days:
                continue
            if scenario_filter and not scenario_filter(a, b):
                continue
            candidates.append(b)
        return candidates

    def score_candidate(
        self,
        a: TransactionFeature,
        b: TransactionFeature,
        emb_similarity: float | None,
    ) -> CandidateScore:
        a_score = amount_score(a.amount, b.amount, self.amount_tolerance)
        d_score = date_score(a.date, b.date, self.date_window_days)
        r_bonus = ref_bonus(a.reference, b.reference)
        rule_score = min(1.0, 0.55 * a_score + 0.35 * d_score + r_bonus)
        final_score = weighted_confidence(rule_score, emb_similarity)
        return CandidateScore(
            transaction_a_id=a.id,
            transaction_b_id=b.id,
            score=final_score,
            algorithm="hybrid_rules_embeddings",
            reason="amount/date/reference + embedding",
            amount_delta=abs(a.amount - b.amount),
            date_delta_days=abs((a.date - b.date).days),
        )

    def tie_break_with_llm(
        self,
        a: TransactionFeature,
        candidates: list[CandidateScore],
        tx_map: dict[str, TransactionFeature],
        llm_client: LLMClient,
    ) -> CandidateScore:
        top = sorted(candidates, key=lambda c: c.score, reverse=True)[:5]
        if len(top) <= 1:
            return top[0]

        source_txn = tx_map[a.id].__dict__
        candidate_payload: list[dict[str, Any]] = []
        for c in top:
            t = tx_map[c.transaction_b_id]
            candidate_payload.append(
                {
                    "id": t.id,
                    "score": c.score,
                    "amount": str(t.amount),
                    "date": str(t.date),
                    "counterparty": t.counterparty,
                    "reference": t.reference,
                }
            )

        response = llm_client.complete_json(build_tiebreak_prompt(source_txn, candidate_payload))
        idx = int(response.get("recommended_match_index", 0))
        idx = max(0, min(idx, len(top) - 1))
        selected = top[idx]
        selected.score = max(selected.score, float(response.get("suggested_confidence", selected.score)))
        selected.reason = str(response.get("reason", selected.reason))
        selected.algorithm = "hybrid_rules_embeddings_llm_tiebreak"
        return selected


def to_feature(txn: TransactionNormalized) -> TransactionFeature:
    return TransactionFeature(
        id=txn.id,
        side=txn.side,
        date=txn.transaction_date,
        amount=txn.amount,
        currency=txn.currency,
        description=txn.description_clean,
        counterparty=txn.counterparty_normalized,
        reference=txn.reference_number,
        account_id=txn.account_id,
        scenario_type=txn.scenario_type.value,
    )
