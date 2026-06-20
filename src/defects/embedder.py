from typing import List, Protocol, runtime_checkable

from src.config import EMBEDDING_MODEL


@runtime_checkable
class Embedder(Protocol):
    def embed(self, text: str) -> List[float]: ...


class LocalEmbedder:
    """Embedder local (HuggingFace). Carga el modelo de forma perezosa (no en import)."""

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        self._model_name = model_name
        self._hf = None

    def embed(self, text: str) -> List[float]:
        if self._hf is None:
            from langchain_huggingface import HuggingFaceEmbeddings
            self._hf = HuggingFaceEmbeddings(model_name=self._model_name)
        return self._hf.embed_query(text)
