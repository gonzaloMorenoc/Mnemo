from src.certify.render import render_html

_CERT = {
    "schema": "mnemo.cert.v1",
    "identity": {"org_id": "o", "project": "web", "commit_sha": "abc123",
                 "run_id": "r1", "created_at": "2026-06-25T00:00:00Z",
                 "mnemo_version": "0.4.0", "model_version": "llama3"},
    "verdict": "no-apto", "risk_score": 72,
    "breakdown": {"real": 2, "flaky": 1, "maintenance": 0, "infra": 0, "unknown": 0},
    "evidence": [{"failure_id": "fa", "category": "real", "confidence": 0.9,
                  "rule_applied": "R5_real_novel", "requires_approval": False}],
    "sign_offs": [], "self_eval": None,
}


def test_render_contains_key_fields():
    html = render_html(_CERT, "sig-b64")
    assert "<html" in html.lower()
    assert "no-apto" in html and "72" in html
    assert "web" in html and "abc123" in html
    assert "real" in html and "fa" in html
    assert "sig-b64" in html


def test_render_escapes_nothing_breaks_on_empty_evidence():
    cert = {**_CERT, "evidence": [], "verdict": "apto", "risk_score": 0}
    html = render_html(cert, "s")
    assert "apto" in html
