from typing import Any, Dict, Protocol, runtime_checkable

from src.config import MODEL_NAME, OLLAMA_BASE_URL


@runtime_checkable
class Narrator(Protocol):
    def summarize(self, verdict: Dict[str, Any]) -> str: ...


class LocalNarrator:
    """Narrativa via Ollama local. Carga el LLM de forma perezosa."""

    def __init__(self, model_name: str = MODEL_NAME):
        self._model_name = model_name
        self._llm = None

    def summarize(self, verdict: Dict[str, Any]) -> str:
        if self._llm is None:
            from langchain_ollama import OllamaLLM
            self._llm = OllamaLLM(model=self._model_name, base_url=OLLAMA_BASE_URL)
        recurring = [f["title"] for f in verdict.get("top_families", []) if f.get("recurring")]
        prompt = (
            "Eres un asistente de aseguramiento de calidad. Resume en 2-3 frases el resultado de un run de tests. "
            f"Datos: {verdict.get('known', 0)} fallos conocidos, {verdict.get('novel', 0)} nuevos, "
            f"riesgo='{verdict.get('risk', 'ok')}'. Familias recurrentes: {recurring or 'ninguna'}."
        )
        return self._llm.invoke(prompt)
