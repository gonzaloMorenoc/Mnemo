class AnthropicProvider:
    """LLM vía API de Anthropic. Carga perezosa."""

    def __init__(self, model: str, api_key: str):
        self._model = model
        self._api_key = api_key
        self._client = None

    def complete(self, prompt: str) -> str:
        if self._client is None:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self._api_key)
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
