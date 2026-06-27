"""Entrypoint de producción de Mnemo Autopilot.

Monta SOLO el API v2 (Autopilot, autenticado). El RAG v1 legacy (`api.py`,
endpoints /analyze,/sync,/history,/stats,/evaluate sin auth) queda deprecated y
FUERA del arranque. El v2 usa getters perezosos, así que no necesita startup_event.
"""
from fastapi import FastAPI

from src.api_v2 import router as v2_router

app = FastAPI(title="Mnemo Autopilot", version="2.0.0")
app.include_router(v2_router)
