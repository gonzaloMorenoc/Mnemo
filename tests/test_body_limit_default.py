"""Tope general de cuerpo en el ASGI (auditoría 23-nov, #17 / H6).

Antes solo /v2/certificates/verify tenía tope: un cuerpo troceado (sin
Content-Length) al webhook de CI se leía entero antes de comprobar la firma."""
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import asgi
from src.http.body_limit import BodySizeLimitMiddleware


def _client_with_default(default=100, per_route=None):
    app = FastAPI()

    @app.post("/v2/cualquiera")
    async def cualquiera(request: Request):
        return {"len": len(await request.body())}

    @app.post("/v2/subida")
    async def subida(request: Request):
        return {"len": len(await request.body())}

    @app.post("/v2/json")
    async def con_modelo(payload: dict):
        return {"keys": len(payload)}

    app.add_middleware(BodySizeLimitMiddleware, default_limit=default,
                       limits=per_route or {"/v2/subida": 1000})
    return TestClient(app)


def _chunks(total, size=40):
    sent = 0
    while sent < total:
        yield b"x" * size
        sent += size


def test_default_limit_applies_to_every_route():
    assert _client_with_default().post("/v2/cualquiera", content=b"x" * 101).status_code == 413


def test_default_limit_cuts_chunked_bodies():
    r = _client_with_default().post("/v2/cualquiera", content=_chunks(400))
    assert r.status_code == 413


def test_chunked_body_parsed_by_fastapi_still_gets_413():
    def body():
        yield b'{"a": "'
        yield from _chunks(400)
        yield b'"}'
    r = _client_with_default().post("/v2/json", content=body(),
                                    headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_per_route_limit_overrides_default():
    c = _client_with_default()
    assert c.post("/v2/subida", content=b"x" * 900).status_code == 200
    assert c.post("/v2/subida", content=b"x" * 1001).status_code == 413


def test_small_bodies_pass_with_default_limit():
    r = _client_with_default().post("/v2/cualquiera", content=b"x" * 50)
    assert r.status_code == 200 and r.json() == {"len": 50}


# --- montado en la app real ---------------------------------------------------

def test_ci_webhook_cuts_chunked_bodies_before_reading_them_whole(monkeypatch):
    import src.api_v2 as api_v2
    from src.config import CI_MAX_BODY_BYTES
    monkeypatch.setattr(api_v2, "CI_SERVICE_ORG_ID", "org-1")
    r = TestClient(asgi.app).post(
        "/v2/ci/webhook", content=_chunks(CI_MAX_BODY_BYTES + 128 * 1024, size=64 * 1024))
    assert r.status_code == 413


def test_every_json_route_has_a_general_limit():
    r = TestClient(asgi.app).post(
        "/v2/orgs", content=_chunks(asgi.DEFAULT_MAX_BODY_BYTES + 128 * 1024, size=64 * 1024),
        headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_upload_routes_keep_their_own_larger_limit():
    for path in asgi.UPLOAD_ROUTES:
        assert asgi.BODY_LIMITS[path] >= asgi.DEFAULT_MAX_BODY_BYTES
    body = b"x" * (asgi.DEFAULT_MAX_BODY_BYTES + 1024)
    r = TestClient(asgi.app).post(
        "/v2/ingest/report", content=body,
        headers={"content-type": "multipart/form-data; boundary=zz"})
    assert r.status_code != 413
