"""¿Puede la memoria del equipo salir a este repo? Solo si es PRIVADO.

En un repo público, el check run y los issues los lee cualquiera. Ante la duda (sin
GitHub, error de red, respuesta rara) se trata como público. Caché corta por repo
para no pedir `GET /repos/…` a GitHub en cada run.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

CACHE_SECONDS = 600
_cache: Dict[str, Tuple[float, bool]] = {}
_lock = threading.Lock()


def repo_is_private(codehost) -> bool:
    check = getattr(codehost, "repo_is_private", None)
    if check is None:
        return False
    key = getattr(codehost, "repo_full_name", None)
    now = time.monotonic()
    if key:
        with _lock:
            hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    try:
        private = check() is True
    except Exception:  # noqa: BLE001
        logger.warning("no se pudo saber si el repo es privado; se trata como público")
        return False   # sin cachear: el próximo run lo vuelve a intentar
    if key:
        with _lock:
            _cache[key] = (now, private)
    return private


def clear_cache() -> None:
    with _lock:
        _cache.clear()
