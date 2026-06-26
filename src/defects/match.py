import math
from dataclasses import dataclass
from typing import List, Optional, Sequence


@dataclass
class FamilyCandidate:
    family_id: str
    signature: str
    centroid: Optional[List[float]] = None


@dataclass
class MatchResult:
    family_id: Optional[str]  # None => crear familia nueva
    is_new: bool
    score: float


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"vector length mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def decide_match(*, fingerprint: str, embedding: Sequence[float],
                 candidates: List[FamilyCandidate], threshold: float = 0.85) -> MatchResult:
    """Empareja un fallo con una familia: firma exacta primero, luego mejor coseno >= threshold."""
    for cand in candidates:
        if cand.signature == fingerprint:
            return MatchResult(family_id=cand.family_id, is_new=False, score=1.0)

    best: Optional[FamilyCandidate] = None
    best_score = 0.0
    for cand in candidates:
        if cand.centroid is None:
            continue
        score = _cosine(embedding, cand.centroid)
        if score > best_score:
            best, best_score = cand, score

    if best is not None and best_score >= threshold:
        return MatchResult(family_id=best.family_id, is_new=False, score=best_score)
    return MatchResult(family_id=None, is_new=True, score=best_score)
