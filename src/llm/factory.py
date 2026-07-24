from typing import Any, Dict

from src import config
from src.llm.provider import LLMProvider
from src.llm.providers.anthropic import AnthropicProvider
from src.llm.providers.ollama import OllamaProvider
from src.llm.providers.openai import OpenAIProvider

_DEFAULT_MODELS = {
    "ollama": "qwen3:8b",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
}


def resolved_model_name() -> str:
    """Nombre del modelo LLM realmente en uso (mismo cálculo que get_llm_provider).
    En prod con Gemini vía OpenAI-compatible, LLM_MODEL viene fijado por env."""
    provider = (config.LLM_PROVIDER or "ollama").strip().lower()
    return config.LLM_MODEL or _DEFAULT_MODELS.get(provider, provider)


def get_llm_provider() -> LLMProvider:
    """Construye el proveedor LLM segun la config de entorno (lazy clients)."""
    provider = (config.LLM_PROVIDER or "ollama").strip().lower()
    model = config.LLM_MODEL or _DEFAULT_MODELS.get(provider, "")
    if provider == "ollama":
        return OllamaProvider(model=model, base_url=config.OLLAMA_BASE_URL)
    if provider in ("openai", "anthropic") and not config.ALLOW_EXTERNAL_LLM:
        raise RuntimeError(
            f"LLM_PROVIDER={provider} envía datos del cliente a un tercero. "
            "Define ALLOW_EXTERNAL_LLM=true para confirmar el envío externo."
        )
    if provider == "openai":
        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY requerida para LLM_PROVIDER=openai")
        return OpenAIProvider(model=model, api_key=config.OPENAI_API_KEY,
                              base_url=config.OPENAI_BASE_URL or None,
                              timeout=config.LLM_TIMEOUT_SECONDS)
    if provider == "anthropic":
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY requerida para LLM_PROVIDER=anthropic")
        return AnthropicProvider(model=model, api_key=config.ANTHROPIC_API_KEY,
                                 max_tokens=config.LLM_MAX_TOKENS)
    raise ValueError(f"LLM_PROVIDER desconocido: {config.LLM_PROVIDER}")


def llm_status(*, probe: bool = False) -> Dict[str, Any]:
    """Diagnóstico del LLM para /v2/health. Distingue dos fallos que hoy se confunden
    en un mudo "LLM no disponible":

    - `configured=False`: el proveedor no se puede construir (falta OPENAI_API_KEY,
      ALLOW_EXTERNAL_LLM no es true, LLM_PROVIDER desconocido…). NO llama a la API.
    - `reachable=False`: el proveedor se construye pero la llamada real falla (401/429/
      timeout/red). Solo se comprueba con `probe=True` (una llamada mínima), porque el
      keep-warm pega `/v2/health` cada 15 min y no queremos gastar cuota ahí.
    """
    provider_name = (config.LLM_PROVIDER or "ollama").strip().lower()
    model = resolved_model_name()
    try:
        provider = get_llm_provider()
    except Exception as exc:  # noqa: BLE001 — reportar el motivo, no ocultarlo
        return {"provider": provider_name, "model": model, "configured": False,
                "reachable": None, "error": str(exc)}
    if not probe:
        return {"provider": provider_name, "model": model, "configured": True,
                "reachable": None, "error": None}
    try:
        provider.complete("ping")
        return {"provider": provider_name, "model": model, "configured": True,
                "reachable": True, "error": None}
    except Exception as exc:  # noqa: BLE001 — el error crudo ES el diagnóstico
        return {"provider": provider_name, "model": model, "configured": True,
                "reachable": False, "error": str(exc)}
