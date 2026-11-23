"""Caché de la narrativa LLM del veredicto (auditoría 2026-11-23, 03-tecnica E8).

`GET /v2/assurance/run/{id}` llamaba al LLM en cada carga de la página. La narrativa
solo depende de los datos del veredicto, así que se cachea por el contenido de ese
veredicto (su «versión de datos»): si cambian los datos del run, cambia la clave y se
regenera. Los fallos del LLM no se cachean. LRU acotada y thread-safe (los endpoints
`def` corren en el threadpool).
"""
import hashlib
import json
import threading
from collections import OrderedDict
from typing import Any, Dict

from src.assurance.narrator import Narrator

NARRATIVE_CACHE_MAX_ENTRIES = 512


def verdict_digest(verdict: Dict[str, Any]) -> str:
    """Huella estable del veredicto: misma entrada → misma clave."""
    canonical = json.dumps(verdict, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CachingNarrator:
    """Envuelve un Narrator y memoiza `summarize` por el contenido del veredicto."""

    def __init__(self, inner: Narrator, max_entries: int = NARRATIVE_CACHE_MAX_ENTRIES):
        if max_entries < 1:
            raise ValueError("max_entries debe ser >= 1")
        self._inner = inner
        self._max_entries = max_entries
        self._cache: "OrderedDict[str, str]" = OrderedDict()
        self._lock = threading.Lock()

    def summarize(self, verdict: Dict[str, Any]) -> str:
        key = verdict_digest(verdict)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        narrative = self._inner.summarize(verdict)   # fuera del lock: puede tardar
        with self._lock:
            self._cache[key] = narrative
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)
        return narrative
