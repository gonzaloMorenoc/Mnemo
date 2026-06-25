import html as _html
from typing import Any, Dict

_VERDICT_COLOR = {"apto": "#1a7f37", "apto-con-reservas": "#9a6700", "no-apto": "#cf222e"}


def _e(v: object) -> str:
    return _html.escape(str(v)) if v is not None else ""


def render_html(cert: Dict[str, Any], signature: str) -> str:
    idn = cert.get("identity", {})
    bd = cert.get("breakdown", {})
    color = _VERDICT_COLOR.get(cert.get("verdict", ""), "#57606a")
    rows = "".join(
        f"<tr><td>{_e(e.get('failure_id'))}</td><td>{_e(e.get('category'))}</td>"
        f"<td>{_e(e.get('confidence'))}</td><td>{_e(e.get('rule_applied'))}</td>"
        f"<td>{'sí' if e.get('requires_approval') else 'no'}</td></tr>"
        for e in cert.get("evidence", [])
    )
    breakdown = ", ".join(f"{k}: {v}" for k, v in bd.items())
    return (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<title>Release Assurance Certificate</title></head><body>"
        "<h1>Release Assurance Certificate</h1>"
        f"<p><strong>Veredicto:</strong> <span style='color:{color}'>{_e(cert.get('verdict'))}</span>"
        f" &middot; <strong>Risk score:</strong> {_e(cert.get('risk_score'))}</p>"
        f"<p>Proyecto <code>{_e(idn.get('project'))}</code> &middot; commit <code>{_e(idn.get('commit_sha'))}</code>"
        f" &middot; run <code>{_e(idn.get('run_id'))}</code> &middot; {_e(idn.get('created_at'))}</p>"
        f"<p>Mnemo {_e(idn.get('mnemo_version'))} &middot; modelo {_e(idn.get('model_version'))}</p>"
        f"<p><strong>Desglose:</strong> {breakdown}</p>"
        "<h2>Evidencia</h2><table border='1' cellpadding='4'>"
        "<tr><th>failure_id</th><th>categoría</th><th>confianza</th><th>regla</th><th>req. aprobación</th></tr>"
        f"{rows}</table>"
        f"<h2>Firma (Ed25519)</h2><pre style='white-space:pre-wrap'>{_e(signature)}</pre>"
        "<p>Verificable con <code>POST /v2/certificates/verify</code> y la clave pública.</p>"
        "</body></html>"
    )
