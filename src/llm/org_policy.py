"""Ámbito de organización de las llamadas al LLM y su política por org.

`ALLOW_EXTERNAL_LLM` es global; el ajuste por org (migración 035) permite a un
cliente excluirse del proveedor externo. Los proveedores son singletons sin org,
así que el endpoint fija la org de los datos que va a mandar al LLM con
`bind_llm_org` (o `bind_llm_org_lazy` si solo tiene el id de un run/familia) y el
guardián (`src/llm/guard.py`) la consulta en cada llamada.

Reglas:
- La org se fija con la org REAL de los datos (la que filtra la consulta), nunca
  con un parámetro libre de la petición que no se use para leer esos datos.
- El ámbito vive en un ContextVar: cada petición (y cada hilo del threadpool, que
  copia el contexto) tiene el suyo; no se filtra entre peticiones.
- Sin org fijada se aplica solo la política global (comportamiento anterior).
- Si la política no se puede leer, se trata como desactivada (falla cerrado).
"""
import logging
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterator, Optional, Tuple

logger = logging.getLogger(__name__)

# Caché corta de la política: una petición puede hacer varias llamadas al LLM
# (propuestas en lote). Un cambio del admin se invalida al instante en este proceso.
POLICY_CACHE_TTL_SECONDS = 30.0


class ExternalLLMDisabledForOrg(RuntimeError):
    """La org ha desactivado el LLM externo: la función de IA degrada a «sin LLM»."""


@dataclass
class _Scope:
    resolver: Callable[[], Optional[str]]
    resolved: bool = False
    org_id: Optional[str] = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def org(self) -> Optional[str]:
        with self.lock:
            if not self.resolved:
                self.org_id = self.resolver()
                self.resolved = True
            return self.org_id


_SCOPE: ContextVar[Optional[_Scope]] = ContextVar("mnemo_llm_org_scope", default=None)


def bind_llm_org(org_id: Optional[str]) -> None:
    """Fija la org de los datos que la petición actual puede mandar al LLM."""
    _SCOPE.set(_Scope(resolver=lambda: org_id, resolved=True, org_id=org_id))


def bind_llm_org_lazy(resolver: Callable[[], Optional[str]]) -> None:
    """Como bind_llm_org, pero la org se resuelve solo si de verdad se llama a un LLM
    externo (p. ej. buscar la org de un run): sin LLM no cuesta una consulta."""
    _SCOPE.set(_Scope(resolver=resolver))


@contextmanager
def llm_org_scope(org_id: Optional[str]) -> Iterator[None]:
    """Ámbito acotado (tareas en segundo plano, scripts, tests)."""
    token = _SCOPE.set(_Scope(resolver=lambda: org_id, resolved=True, org_id=org_id))
    try:
        yield
    finally:
        _SCOPE.reset(token)


def has_llm_org_scope() -> bool:
    return _SCOPE.get() is not None


def current_llm_org() -> Optional[str]:
    """La org fijada para la petición actual (None si no hay ámbito).
    Un fallo al resolverla se propaga: el guardián lo trata como desactivado."""
    scope = _SCOPE.get()
    return None if scope is None else scope.org()


# ---------------------------------------------------------------------------
# Política por org (con caché)
# ---------------------------------------------------------------------------

_cache: Dict[str, Tuple[bool, float]] = {}
_cache_lock = threading.Lock()


def _read_policy_from_db(org_id: str) -> bool:
    from src.config import multi_tenant_enabled
    if not multi_tenant_enabled():
        return True   # self-host sin BD: solo cuenta la política global
    from src.orgs.llm_settings import OrgLlmSettingsRepository
    return OrgLlmSettingsRepository().allows_external_llm(org_id)


def external_llm_allowed(org_id: str, *,
                         reader: Callable[[str], bool] = _read_policy_from_db) -> bool:
    """¿Puede la org mandar datos al LLM externo? Falla cerrado si no se puede leer."""
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(org_id)
    if cached is not None and cached[1] > now:
        return cached[0]
    try:
        allowed = bool(reader(org_id))
    except Exception:  # noqa: BLE001 — falla cerrado, pero con rastro
        logger.exception("no se pudo leer la política de LLM de la org %s: se desactiva", org_id)
        return False
    with _cache_lock:
        _cache[org_id] = (allowed, now + POLICY_CACHE_TTL_SECONDS)
    return allowed


def invalidate_policy_cache(org_id: Optional[str] = None) -> None:
    with _cache_lock:
        if org_id is None:
            _cache.clear()
        else:
            _cache.pop(org_id, None)


def bind_llm_org_of(table: str, row_id: str) -> None:
    """Fija como ámbito la org de una fila (run, familia, acción, propuesta), resuelta
    solo si se llega a llamar al LLM externo. Sin multi-tenant no hay nada que fijar."""
    from src.config import multi_tenant_enabled
    if not multi_tenant_enabled():
        return
    from src.orgs.llm_settings import OrgLlmSettingsRepository
    bind_llm_org_lazy(lambda: OrgLlmSettingsRepository().org_of(table, row_id))
