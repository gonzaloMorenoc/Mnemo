from src.llm.providers.ollama import OllamaProvider
from src.llm.providers.openai import OpenAIProvider
from src.llm.providers.anthropic import AnthropicProvider


def test_ollama_complete_uses_invoke():
    p = OllamaProvider(model="m", base_url="http://x")
    p._llm = type("L", (), {"invoke": staticmethod(lambda prompt: "respuesta ollama")})()
    assert p.complete("hola") == "respuesta ollama"


def test_openai_complete_extracts_content():
    p = OpenAIProvider(model="gpt", api_key="k")
    class _Resp:
        choices = [type("C", (), {"message": type("M", (), {"content": "respuesta openai"})()})()]
    p._client = type("Cli", (), {"chat": type("Ch", (), {"completions": type("Co", (), {
        "create": staticmethod(lambda **kw: _Resp())})()})()})()
    assert p.complete("hola") == "respuesta openai"


def test_anthropic_complete_joins_text_blocks():
    p = AnthropicProvider(model="claude", api_key="k")
    class _Block:
        type = "text"
        text = "respuesta anthropic"
    class _Resp:
        content = [_Block()]
    p._client = type("Cli", (), {"messages": type("M", (), {
        "create": staticmethod(lambda **kw: _Resp())})()})()
    assert p.complete("hola") == "respuesta anthropic"
