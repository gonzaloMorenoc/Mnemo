from typing import Any, Dict, List, Protocol

from src.llm.provider import LLMProvider
from src.llm.reasoning import strip_reasoning


class SelfHealExplainer(Protocol):
    def explain(
        self, *, broken_locator: str, suggested_locator: str, candidates: List[Dict[str, Any]]
    ) -> str: ...


def _build_prompt(broken_locator: str, suggested_locator: str, candidates: List[Dict[str, Any]]) -> str:
    alts = "\n".join(f"- {c['locator']} (score {c['score']}, {c['why']})" for c in candidates[:5])
    return (
        "Eres un ingeniero de QA. Un locator de Playwright dejó de resolver porque el DOM cambió. "
        "Explica en 1-2 frases por qué el locator sugerido es más robusto que el roto. "
        "Básate SOLO en los datos, no inventes.\n\n"
        f"Locator roto: {broken_locator}\n"
        f"Locator sugerido: {suggested_locator}\n"
        f"Candidatos:\n{alts}\n"
    )


class LLMSelfHealExplainer:
    def __init__(self, provider: LLMProvider):
        self._provider = provider

    def explain(self, *, broken_locator: str, suggested_locator: str, candidates) -> str:
        return strip_reasoning(
            self._provider.complete(_build_prompt(broken_locator, suggested_locator, candidates))
        )
