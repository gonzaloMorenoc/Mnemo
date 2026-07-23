"""El SDK de OpenAI por defecto = 600 s × 3 reintentos → un hilo del worker único
retenido 30+ min. El provider DEBE fijar timeout y max_retries=0 explícitos."""
from unittest.mock import MagicMock, patch

from src.llm.providers.openai import OpenAIProvider


def test_openai_client_created_with_timeout_and_no_retries():
    provider = OpenAIProvider(model="m", api_key="k", timeout=50)
    with patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(choices=[])
        mock_openai.return_value = mock_client
        provider.complete("hola")
    kwargs = mock_openai.call_args.kwargs
    assert kwargs["timeout"] == 50
    assert kwargs["max_retries"] == 0


def test_config_default_is_50_seconds():
    from src.config import LLM_TIMEOUT_SECONDS
    assert LLM_TIMEOUT_SECONDS == 50


def test_factory_pasa_el_timeout_al_provider():
    """La factoría debe construir el provider OpenAI con el timeout de config."""
    from unittest.mock import patch as _patch

    with _patch("src.llm.factory.OpenAIProvider") as mock_provider, \
         _patch("src.llm.factory.config") as mock_config:
        mock_config.LLM_PROVIDER = "openai"
        mock_config.LLM_MODEL = "m"
        mock_config.OPENAI_API_KEY = "k"
        mock_config.OPENAI_BASE_URL = ""
        mock_config.LLM_TIMEOUT_SECONDS = 50
        from src.llm.factory import get_llm_provider
        get_llm_provider()
    assert mock_provider.call_args.kwargs.get("timeout") == 50
