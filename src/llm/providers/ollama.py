class OllamaProvider:
    """LLM local vía Ollama (langchain_ollama). Carga perezosa."""

    def __init__(self, model: str, base_url: str):
        self._model = model
        self._base_url = base_url
        self._llm = None

    def complete(self, prompt: str) -> str:
        if self._llm is None:
            from langchain_ollama import OllamaLLM
            self._llm = OllamaLLM(model=self._model, base_url=self._base_url)
        return self._llm.invoke(prompt)
