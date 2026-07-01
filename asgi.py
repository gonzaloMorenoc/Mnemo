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

from src.api_v2 import router as v2_router
from src.db.pool import get_pool, close_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        get_pool()          # pre-calienta el pool; si la BD no está, no tumbar el arranque
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("pool pre-warm failed; lazy init on first request: %s", exc)
    yield
    close_pool()


app = FastAPI(title="Mnemo Autopilot", version="2.0.0", lifespan=lifespan)
app.include_router(v2_router)
