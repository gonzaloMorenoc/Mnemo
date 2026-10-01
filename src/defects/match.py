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


# Coseno mínimo para fusionar un fallo en una familia existente sin firma exacta.
# Calibrado el 30-sep con el modelo multilingüe (tests/golden/familias_pares.py):
# ningún umbral separa del todo, porque el modelo ve la FORMA del mensaje y no su
# objetivo (dos ECONNREFUSED a servicios distintos dan 0,82-0,85). Fusionar dos
# defectos distintos corrompe la memoria —el nuevo hereda la etiqueta y la razón
# del viejo, y con R0 un defecto real podría heredar un 'flaky'—; partir uno solo
# cuesta etiquetarlo dos veces. Ante la duda, no fusionar: 0,85 fusionaba 3/10
# pares distintos, 0,90 fusiona 1/10 (y 7/10 de los iguales).
MATCH_THRESHOLD = 0.90


def decide_match(*, fingerprint: str, embedding: Sequence[float],
                 candidates: List[FamilyCandidate],
                 threshold: float = MATCH_THRESHOLD) -> MatchResult:
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
