from src import config
from src.llm.provider import LLMProvider
from src.llm.providers.anthropic import AnthropicProvider
from src.llm.providers.ollama import OllamaProvider
from src.llm.providers.openai import OpenAIProvider


def get_llm_provider() -> LLMProvider:
    """Construye el proveedor LLM segun la config de entorno (lazy clients)."""
    provider = (config.LLM_PROVIDER or "ollama").lower()
    if provider == "ollama":
        return OllamaProvider(model=config.LLM_MODEL, base_url=config.OLLAMA_BASE_URL)
    if provider == "openai":
        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY requerida para LLM_PROVIDER=openai")
        return OpenAIProvider(model=config.LLM_MODEL, api_key=config.OPENAI_API_KEY,
                              base_url=config.OPENAI_BASE_URL or None)
    if provider == "anthropic":
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY requerida para LLM_PROVIDER=anthropic")
        return AnthropicProvider(model=config.LLM_MODEL, api_key=config.ANTHROPIC_API_KEY)
    raise ValueError(f"LLM_PROVIDER desconocido: {config.LLM_PROVIDER}")
