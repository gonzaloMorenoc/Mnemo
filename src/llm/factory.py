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
