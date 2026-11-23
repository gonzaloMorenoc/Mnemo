import threading
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from src.config import EMBEDDING_MODEL


@runtime_checkable
class Embedder(Protocol):
    def embed(self, text: str) -> List[float]: ...


def _load_hf(model_name: str) -> Any:
    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(model_name=model_name)


# Un ÚNICO modelo por (proceso, nombre): cada copia de torch ocupa cientos de MB y
# cargarla desde disco tarda segundos. Antes cada LocalEmbedder() cargaba la suya
# (5-6 copias en RAM y una por petición en /automation/generate y /repo/index).
_hf_factory: Callable[[str], Any] = _load_hf
_models: Dict[str, Any] = {}
_models_lock = threading.Lock()


def _get_model(model_name: str) -> Any:
    """Modelo compartido, carga perezosa thread-safe (lock con doble comprobación)."""
    model = _models.get(model_name)
    if model is not None:
        return model
    with _models_lock:
        model = _models.get(model_name)
        if model is None:
            model = _hf_factory(model_name)
            _models[model_name] = model
    return model


class LocalEmbedder:
    """Embedder local (HuggingFace). Carga el modelo de forma perezosa (no en import) y
    lo comparte con todas las instancias del proceso que usen el mismo modelo."""

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        self._model_name = model_name
        self._hf = None

    def embed(self, text: str) -> List[float]:
        if self._hf is None:
            self._hf = _get_model(self._model_name)
        return self._hf.embed_query(text)


_shared: Optional[LocalEmbedder] = None
_shared_lock = threading.Lock()


def get_shared_embedder() -> LocalEmbedder:
    """El embedder del proceso: lo inyectan todos los servicios y repositorios."""
    global _shared
    if _shared is None:
        with _shared_lock:
            if _shared is None:
                _shared = LocalEmbedder()
    return _shared
