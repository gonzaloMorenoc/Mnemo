import re
from typing import Any, Dict, Optional, Tuple

from src.llm.factory import get_llm_provider
from src.llm.provider import LLMProvider
from src.llm.reasoning import strip_reasoning

_VALID = ("flaky", "infra", "maintenance", "real")


def parse_category(text: str) -> Optional[str]:
    """Extrae la categoría de la respuesta del LLM: la primera de las 4 válidas
    que aparezca como palabra (case-insensitive). None si no hay ninguna."""
    if not text:
        return None
    low = text.lower()
    best_cat: Optional[str] = None
    best_pos = len(low) + 1
    for cat in _VALID:
        m = re.search(rf"\b{cat}\b", low)
        if m and m.start() < best_pos:
            best_pos = m.start()
            best_cat = cat
    return best_cat


def _build_prompt(evidence: Dict[str, Any]) -> str:
    signals = evidence.get("signals", []) or []
    active = [s.get("name") for s in signals if s.get("value")]
    return (
        "Eres un ingeniero de QA clasificando un fallo de test que el motor "
        "determinista no pudo clasificar. Elige EXACTAMENTE una categoría:\n"
        "- flaky: pasa/falla de forma intermitente sin cambios reales.\n"
        "- infra: problema de entorno, red o infraestructura.\n"
        "- maintenance: el test está desactualizado (la app cambió de forma legítima).\n"
        "- real: defecto real del producto.\n\n"
        f"error_type: {evidence.get('error_type')}\n"
        f"señales activas: {', '.join(a for a in active if a) or 'ninguna'}\n"
        f"regla determinista: {evidence.get('rule_applied')}\n\n"
        "Responde empezando por la categoría (una de: flaky, infra, maintenance, real) "
        "y luego una razón breve en una frase."
    )


class LLMTiebreaker:
    """Desempata un ambiguo con el LLM. Degrada a None si el LLM falla o no decide.
    El provider se obtiene de forma perezosa (no en __init__) salvo que se inyecte."""

    def __init__(self, provider: Optional[LLMProvider] = None):
        self._provider = provider

    def resolve(self, evidence: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        try:
            provider = self._provider or get_llm_provider()
            raw = strip_reasoning(provider.complete(_build_prompt(evidence)))
        except Exception:  # noqa: BLE001 — el tiebreak degrada; nunca propaga
            return None
        category = parse_category(raw)
        if category is None:
            return None
        return category, (raw or "").strip()[:1000]
