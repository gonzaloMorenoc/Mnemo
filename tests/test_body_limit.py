"""Tope de tamaño de cuerpo ANTES de leerlo, para los endpoints públicos sin auth.

POST /v2/certificates/verify es público y su `canonical_json` es un dict sin tope:
sin esto, cualquiera podía obligar al único proceso a leer y serializar cuerpos
enormes. FastAPI lee el cuerpo antes de resolver las dependencias, así que el
freno tiene que estar en el ASGI."""
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.http.body_limit import BodySizeLimitMiddleware


def _client(limit=100):
    app = FastAPI()

    @app.post("/v2/certificates/verify")
    async def verify(request: Request):
        return {"len": len(await request.body())}

    @app.post("/v2/otra")
    async def otra(request: Request):
        return {"len": len(await request.body())}

    app.add_middleware(BodySizeLimitMiddleware, limits={"/v2/certificates/verify": limit})
    return TestClient(app)


def test_rejects_by_content_length_before_reading():
    r = _client().post("/v2/certificates/verify", content=b"x" * 101)
    assert r.status_code == 413


def test_rejects_a_chunked_body_that_grows_past_the_limit():
    def chunks():
        for _ in range(5):
            yield b"x" * 40   # sin Content-Length: 200 bytes en trozos
    r = _client().post("/v2/certificates/verify", content=chunks())
    assert r.status_code == 413


def test_lets_through_bodies_under_the_limit():
    r = _client().post("/v2/certificates/verify", content=b"x" * 100)
    assert r.status_code == 200 and r.json() == {"len": 100}


def test_other_paths_are_not_limited():
    r = _client().post("/v2/otra", content=b"x" * 1000)
    assert r.status_code == 200
