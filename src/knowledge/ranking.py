"""Orden de las fuentes de la búsqueda unificada (auditoría 23-nov, #8). Puro.

Conocimiento y familias se mezclan por distancia (menor = más relevante). Las
familias con la razón del etiquetador o con una lección vinculada son lo que
distingue a Mnemo de una wiki, así que tienen un mínimo de huecos reservado
dentro del corte que llega al LLM (MAX_CONTEXT_SOURCES), aunque haya muchos
items de conocimiento algo más cercanos. Nada se descarta: lo que no entra en
el corte va detrás, también por distancia (la búsqueda de la UI lo sigue viendo).
"""
from typing import Any, Dict, List, Sequence

from src.ai.generate import MAX_CONTEXT_SOURCES

# Huecos mínimos del corte para familias con razón o lección (si las hay).
MIN_FAMILY_SLOTS = 3

_NO_DISTANCE = float("inf")


def _dist(source: Dict[str, Any]) -> float:
    d = source.get("dist")
    return _NO_DISTANCE if d is None else float(d)


def _by_distance(sources: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(sources, key=_dist)  # sorted es estable: empates conservan su orden


def merge_by_relevance(knowledge: Sequence[Dict[str, Any]], families: Sequence[Dict[str, Any]],
                       *, limit: int = MAX_CONTEXT_SOURCES,
                       min_family_slots: int = MIN_FAMILY_SLOTS) -> List[Dict[str, Any]]:
    """Fuentes ordenadas: primero las `limit` elegidas (por distancia, con las
    familias prioritarias garantizadas), después el resto por distancia."""
    ranked = _by_distance([*knowledge, *families])
    reserved = [f for f in _by_distance(families) if f.get("priority")][:min(min_family_slots, limit)]
    reserved_ids = {id(f) for f in reserved}
    others = [s for s in ranked if id(s) not in reserved_ids]
    head = _by_distance([*reserved, *others[:max(0, limit - len(reserved))]])
    head_ids = {id(s) for s in head}
    return [*head, *(s for s in ranked if id(s) not in head_ids)]
