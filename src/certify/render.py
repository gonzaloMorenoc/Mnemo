from typing import Any, Dict

_VERDICT_COLOR = {"apto": "#1a7f37", "apto-con-reservas": "#9a6700", "no-apto": "#cf222e"}


def render_html(cert: Dict[str, Any], signature: str) -> str:
    idn = cert.get("identity", {})
    bd = cert.get("breakdown", {})
    color = _VERDICT_COLOR.get(cert.get("verdict", ""), "#57606a")
    rows = "".join(
        f"<tr><td>{e.get('failure_id')}</td><td>{e.get('category')}</td>"
        f"<td>{e.get('confidence')}</td><td>{e.get('rule_applied')}</td>"
        f"<td>{'sí' if e.get('requires_approval') else 'no'}</td></tr>"
        for e in cert.get("evidence", [])
    )
    breakdown = ", ".join(f"{k}: {v}" for k, v in bd.items())
    return (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<title>Release Assurance Certificate</title></head><body>"
        "<h1>Release Assurance Certificate</h1>"
        f"<p><strong>Veredicto:</strong> <span style='color:{color}'>{cert.get('verdict')}</span>"
        f" &middot; <strong>Risk score:</strong> {cert.get('risk_score')}</p>"
        f"<p>Proyecto <code>{idn.get('project')}</code> &middot; commit <code>{idn.get('commit_sha')}</code>"
        f" &middot; run <code>{idn.get('run_id')}</code> &middot; {idn.get('created_at')}</p>"
        f"<p>Mnemo {idn.get('mnemo_version')} &middot; modelo {idn.get('model_version')}</p>"
        f"<p><strong>Desglose:</strong> {breakdown}</p>"
        "<h2>Evidencia</h2><table border='1' cellpadding='4'>"
        "<tr><th>failure_id</th><th>categoría</th><th>confianza</th><th>regla</th><th>req. aprobación</th></tr>"
        f"{rows}</table>"
        f"<h2>Firma (Ed25519)</h2><pre style='white-space:pre-wrap'>{signature}</pre>"
        "<p>Verificable con <code>POST /v2/certificates/verify</code> y la clave pública.</p>"
        "</body></html>"
    )
