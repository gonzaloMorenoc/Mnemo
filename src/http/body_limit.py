"""Tope de tamaño del cuerpo, aplicado en el ASGI ANTES de leer el cuerpo.

FastAPI lee el cuerpo antes de resolver dependencias y validar el modelo, así que
un límite dentro del endpoint llega tarde: el proceso ya ha leído (y luego
serializaría) lo que le manden. Aquí se corta por Content-Length y, si el cuerpo
llega troceado sin cabecera, contando bytes según entran.

`default_limit` se aplica a toda ruta sin tope propio en `limits` (auditoría
23-nov, H6: antes solo una ruta tenía tope y el webhook de CI leía entero un
cuerpo troceado antes de comprobar la firma).
"""
import json
from typing import Dict, Optional

from fastapi import HTTPException

_TOO_LARGE_STATUS = 413


class _TooLarge(HTTPException):
    """HTTPException para que, si el corte ocurre mientras FastAPI parsea el cuerpo
    (JSON o formulario), su manejador lo deje pasar como 413 y no como un 400
    genérico de «error al parsear el cuerpo»."""

    def __init__(self, limit: int):
        super().__init__(status_code=_TOO_LARGE_STATUS,
                         detail=f"Cuerpo demasiado grande (máximo {limit} bytes).")


class BodySizeLimitMiddleware:
    def __init__(self, app, *, limits: Dict[str, int], default_limit: Optional[int] = None):
        self.app = app
        self.limits = limits
        self.default_limit = default_limit

    def _limit_for(self, scope) -> Optional[int]:
        if scope["type"] != "http":
            return None
        return self.limits.get(scope.get("path", ""), self.default_limit)

    async def __call__(self, scope, receive, send):
        limit = self._limit_for(scope)
        if limit is None:
            await self.app(scope, receive, send)
            return
        length = dict(scope.get("headers") or []).get(b"content-length")
        if length is not None and length.isdigit() and int(length) > limit:
            await _reject(send, limit)
            return

        seen = 0

        async def counting_receive():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    raise _TooLarge(limit)
            return message

        started = False

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _TooLarge:
            if not started:
                await _reject(send, limit)


async def _reject(send, limit: int) -> None:
    body = json.dumps({"detail": f"Cuerpo demasiado grande (máximo {limit} bytes)."}).encode()
    await send({"type": "http.response.start", "status": _TOO_LARGE_STATUS,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
