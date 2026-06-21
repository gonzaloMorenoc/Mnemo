from typing import Optional


class OpenAIProvider:
    """LLM vía API compatible OpenAI (OpenAI, Azure, Groq, vLLM...). Carga perezosa."""

    def __init__(self, model: str, api_key: str, base_url: Optional[str] = None):
        self._model = model
        self._api_key = api_key
        self._base_url = base_url or None
        self._client = None

    def complete(self, prompt: str) -> str:
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""
