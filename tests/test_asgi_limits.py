"""El tope de cuerpo está montado en la app real, no solo probado en aislado."""
from fastapi.testclient import TestClient

import asgi


def test_public_verify_rejects_huge_bodies_before_reading():
    c = TestClient(asgi.app)
    r = c.post("/v2/certificates/verify", content=b"{" + b" " * (600 * 1024) + b"}",
               headers={"content-type": "application/json"})
    assert r.status_code == 413
