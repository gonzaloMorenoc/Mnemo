"""Límite de peticiones por token: cubo de fichas en memoria.

El backend es UN proceso (Space de HF), así que basta con memoria local; al reiniciar,
los cubos empiezan llenos, que es lo seguro para el usuario y suficiente contra abuso.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Tuple

MAX_BUCKETS = 10_000   # tope de memoria: tokens distintos vistos recientemente


class TokenBucket:
    def __init__(self, *, per_minute: int, burst: int,
                 clock: Callable[[], float] = time.monotonic):
        self._rate = max(per_minute, 1) / 60.0
        self._burst = float(max(burst, 1))
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets: Dict[str, Tuple[float, float]] = {}   # clave → (fichas, instante)

    def take(self, key: str) -> float:
        """Consume una ficha. Devuelve 0 si se permite; si no, los segundos a esperar."""
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.get(key, (self._burst, now))
            tokens = min(self._burst, tokens + (now - last) * self._rate)
            if tokens >= 1.0:
                self._store(key, (tokens - 1.0, now))
                return 0.0
            self._store(key, (tokens, now))
            return (1.0 - tokens) / self._rate

    def _store(self, key: str, value: Tuple[float, float]) -> None:
        if key not in self._buckets and len(self._buckets) >= MAX_BUCKETS:
            # El más antiguo fuera: un cubo olvidado vuelve lleno, nunca bloquea de más.
            oldest = min(self._buckets, key=lambda k: self._buckets[k][1])
            del self._buckets[oldest]
        self._buckets[key] = value
