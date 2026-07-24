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


def test_render_pdf_returns_pdf_bytes():
    from src.certify.render import render_pdf
    cert = {
        "verdict": "apto", "risk_score": 12,
        "identity": {"project": "demo", "commit_sha": "abc123", "run_id": "r1",
                     "created_at": "2026-06-27", "mnemo_version": "1.0", "model_version": "m1"},
        "breakdown": {"real": 1}, "evidence": [], "self_eval": {},
    }
    out = render_pdf(cert, "SIG==")
    assert isinstance(out, bytes)
    assert out[:5] == b"%PDF-"


def test_render_html_pulido_mantiene_contenido_y_marca():
    from src.certify.render import render_html
    html = render_html({"verdict": "apto", "risk_score": 12, "identity": {}, "breakdown": {},
                        "evidence": [], "self_eval": {}}, "SIG==")
    assert "Mnemo" in html
    assert "apto" in html
    assert "SIG==" in html  # la firma


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


def test_render_sin_confirmar_no_muestra_risk_0_y_pinta_manifiesto():
    cert = {
        "verdict": "sin_confirmar", "risk_score": 0,
        "identity": {"project": "web", "commit_sha": "c", "run_id": "r", "created_at": "t",
                     "mnemo_version": "1", "model_version": "m"},
        "breakdown": {}, "evidence": [], "sign_offs": [], "self_eval": None,
        "execution_manifest": {"total": 128, "passed": 120, "failed": 5, "skipped": 3,
                               "flaky": 0, "complete": True, "source_format": "junit"},
    }
    html = render_html(cert, "sig")
    # Riesgo NO debe ser "0" para sin_confirmar; usa la raya (—)
    assert "Risk score:</strong> 0" not in html
    assert "&mdash;" in html
    assert "no prueba una ejecución completa" in html
    # El manifiesto SÍ aparece en el acta descargable
    assert "128 tests" in html and "junit" in html
