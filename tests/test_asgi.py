from fastapi.testclient import TestClient

import asgi


def test_asgi_serves_v2_health():
    client = TestClient(asgi.app)
    r = client.get("/v2/health")
    assert r.status_code == 200


def test_asgi_does_not_expose_legacy_analyze():
    client = TestClient(asgi.app)
    # el endpoint legacy /analyze (RAG v1, sin auth) NO debe existir en el entrypoint nuevo
    assert client.post("/analyze", json={"error_log": "x"}).status_code == 404
    assert client.get("/history").status_code == 404
