"""Tope de tamaño del cuerpo por ruta, aplicado en el ASGI ANTES de leer el cuerpo.

FastAPI lee el cuerpo antes de resolver dependencias y validar el modelo, así que
un límite dentro del endpoint llega tarde: el proceso ya ha leído (y luego
serializaría) lo que le manden. Aquí se corta por Content-Length y, si el cuerpo
llega troceado sin cabecera, contando bytes según entran.
"""
import json
from typing import Dict


class _TooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(self, app, *, limits: Dict[str, int]):
        self.app = app
        self.limits = limits

    async def __call__(self, scope, receive, send):
        limit = self.limits.get(scope.get("path", "")) if scope["type"] == "http" else None
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
                    raise _TooLarge()
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
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
