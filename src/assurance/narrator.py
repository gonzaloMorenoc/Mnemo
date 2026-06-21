from typing import Any, Dict, Protocol, runtime_checkable

from src.llm.provider import LLMProvider
from src.llm.reasoning import strip_reasoning


@runtime_checkable
class Narrator(Protocol):
    def summarize(self, verdict: Dict[str, Any]) -> str: ...


class LLMNarrator:
    """Narrativa del veredicto vía un LLMProvider intercambiable."""

    def __init__(self, provider: LLMProvider):
        self._provider = provider

    def summarize(self, verdict: Dict[str, Any]) -> str:
        recurring = [f["title"] for f in verdict.get("top_families", []) if f.get("recurring")]
        prompt = (
            "Eres un asistente de aseguramiento de calidad. Resume en 2-3 frases el resultado de un run de tests. "
            f"Datos: {verdict.get('known', 0)} fallos conocidos, {verdict.get('novel', 0)} nuevos, "
            f"riesgo='{verdict.get('risk', 'ok')}'. Familias recurrentes: {recurring or 'ninguna'}."
        )
        return strip_reasoning(self._provider.complete(prompt))
