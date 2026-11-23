"""Entrypoint de producción de Mnemo Autopilot.

Monta SOLO el API v2 (Autopilot, autenticado). El RAG v1 legacy (`api.py`,
endpoints /analyze,/sync,/history,/stats,/evaluate sin auth) queda deprecated y
FUERA del arranque.

El lifespan pre-calienta el pool de BD en el arranque para que las primeras
peticiones no paguen el coste de conexión (~1-8 s). Si la BD no está disponible
al arrancar, el error se absorbe (try/except) para no tumbar el contenedor.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.logging_config import configure_logging

configure_logging()     # antes de importar la app: que sus logger.info no se pierdan

from src.api_v2 import router as v2_router  # noqa: E402
from src.config import CI_MAX_BODY_BYTES, INGEST_MAX_BYTES, api_docs_exposed  # noqa: E402
from src.orgs.api import router as orgs_members_router  # noqa: E402
from src.db.pool import get_pool, close_pool  # noqa: E402
from src.http.body_limit import BodySizeLimitMiddleware  # noqa: E402
from src.defects.embedder import get_shared_embedder  # noqa: E402
from src.knowledge.chunk_backfill import start_backfill_in_background  # noqa: E402

# Tope GENERAL de cuerpo para toda ruta (también troceada, sin Content-Length): se
# corta en el ASGI mientras entra, antes de que FastAPI o el endpoint lo lean entero.
# 2 MiB sobra para cualquier JSON de la API (planes, código de un test, conocimiento).
DEFAULT_MAX_BODY_BYTES = 2 * 1024 * 1024
# Margen para las cabeceras multipart alrededor del fichero (mismo que /ci/ingest).
_MULTIPART_MARGIN_BYTES = 64 * 1024
UPLOAD_MAX_BODY_BYTES = INGEST_MAX_BYTES + _MULTIPART_MARGIN_BYTES
# Excepción documentada: las rutas de SUBIDA tienen su propio tope (INGEST_MAX_BYTES,
# comprobado también dentro del endpoint), mayor que el general; aquí se fija ese
# tope + margen multipart para que un cuerpo troceado tampoco lo supere.
UPLOAD_ROUTES = ("/v2/ingest/report", "/v2/ingest/jira/file",
                 "/v2/test-plan/generate", "/v2/ci/ingest")
BODY_LIMITS = {
    **{path: UPLOAD_MAX_BODY_BYTES for path in UPLOAD_ROUTES},
    # Webhook de CI: su propio tope (CI_MAX_BODY_BYTES), ahora también para troceados.
    "/v2/ci/webhook": CI_MAX_BODY_BYTES,
    # Público y sin auth: un acta real ocupa ~2 KB; 512 KB deja margen para runs con
    # cientos de fallos en la evidencia.
    "/v2/certificates/verify": 512 * 1024,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        pool = get_pool()   # pre-calienta el pool; si la BD no está, no tumbar el arranque
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("pool pre-warm failed; lazy init on first request: %s", exc)
    else:
        # Fragmentos del conocimiento que falten (migración 033): en segundo plano, sin
        # paso manual tras desplegar.
        start_backfill_in_background(pool.connection, get_shared_embedder)
    yield
    close_pool()


def create_app(*, expose_api_docs: bool) -> FastAPI:
    docs = {} if expose_api_docs else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    application = FastAPI(title="Mnemo Autopilot", version="2.0.0", lifespan=lifespan, **docs)
    application.include_router(v2_router)
    application.include_router(orgs_members_router)
    application.add_middleware(BodySizeLimitMiddleware, limits=BODY_LIMITS,
                               default_limit=DEFAULT_MAX_BODY_BYTES)
    return application


app = create_app(expose_api_docs=api_docs_exposed())
