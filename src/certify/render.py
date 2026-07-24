import html as _html
from io import BytesIO
from typing import Any, Dict

_VERDICT_COLOR = {"apto": "#1a7f37", "apto-con-reservas": "#9a6700", "no-apto": "#cf222e",
                  "sin_confirmar": "#57606a"}
_MTP_BLUE = "#101246"


def _e(v: object) -> str:
    return _html.escape(str(v)) if v is not None else ""


def _rule_label(rule: object) -> str:
    return "real (sin precedente en el histórico)" if rule == "R5_real_novel" else (str(rule) if rule is not None else "")


def render_html(cert: Dict[str, Any], signature: str, public_url: str = "") -> str:
    idn = cert.get("identity", {})
    bd = cert.get("breakdown", {})
    verdict = cert.get("verdict", "")
    color = _VERDICT_COLOR.get(verdict, "#57606a")
    # Un run "sin_confirmar" no tiene riesgo que reportar (no se pudo confirmar la ejecución).
    risk_html = "&mdash;" if verdict == "sin_confirmar" else _e(cert.get("risk_score"))

    # Manifiesto de ejecución (acta v3); ausente en actas v2.
    m = cert.get("execution_manifest") or {}
    manifest_html = (
        f"<p><strong>Ejecución:</strong> {_e(m.get('total'))} tests &middot; "
        f"{_e(m.get('passed'))} pasados &middot; {_e(m.get('failed'))} fallidos &middot; "
        f"{_e(m.get('skipped'))} omitidos"
        + (f" &middot; {_e(m.get('flaky'))} flaky" if m.get("flaky") else "")
        + f" &middot; formato <code>{_e(m.get('source_format'))}</code></p>"
    ) if m else ""
    sin_confirmar_note = (
        "<p style='color:#57606a'>El reporte no prueba una ejecución completa; "
        "el acta lo refleja.</p>" if verdict == "sin_confirmar" else ""
    )
    rows = "".join(
        f"<tr><td>{_e(e.get('failure_id'))}</td><td>{_e(e.get('category'))}</td>"
        f"<td>{_e(e.get('confidence'))}</td><td>{_e(_rule_label(e.get('rule_applied')))}</td>"
        f"<td>{'sí' if e.get('requires_approval') else 'no'}</td></tr>"
        for e in cert.get("evidence", [])
    )
    breakdown = ", ".join(f"{_e(k)}: {_e(v)}" for k, v in bd.items())

    # Disclaimer paragraph
    disclaimer_html = f"<p style='font-size:0.9em;color:#57606a'>{_e(cert.get('disclaimer'))}</p>" if cert.get('disclaimer') else ""

    # Self-evaluation block
    se = cert.get("self_eval") or {}
    cal = se.get("engine_calibration", {})
    self_eval_html = (
        f"<h2>Auto-evaluación del motor</h2>"
        f"<p>Confianza: <strong>{_e(se.get('confidence'))}</strong> &middot; "
        f"precisión del motor en este cliente: {_e(cal.get('tenant_accuracy'))} "
        f"(n={_e(cal.get('n_corrections'))} correcciones)</p>"
    ) if se else ""

    key_id = _e(idn.get("key_id"))
    firma_html = (f"<p>Firmada con la clave <code>{key_id}</code>.</p>" if key_id else "")
    verificable = (
        f"<p>Verificable en <code>{_e(public_url)}/verify</code>, sin cuenta.</p>"
        if public_url else
        "<p>Verificable en la página pública «Verificar acta» de Mnemo, sin cuenta.</p>"
    )

    return (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<title>Release Assurance Certificate</title>"
        "<style>"
        "@page { margin: 1.8cm; }"
        "body { font-family: Helvetica, Arial, sans-serif; color: #24292f; font-size: 11pt; }"
        ".brand { font-size: 9pt; letter-spacing: 2px; color: #57606a; text-transform: uppercase; }"
        "h1 { font-size: 18pt; margin: 2px 0 10px 0; }"
        "h2 { font-size: 13pt; border-bottom: 1px solid #d0d7de; padding-bottom: 3px; margin-top: 18px; }"
        ".verdict { font-size: 15pt; font-weight: bold; }"
        "table { border-collapse: collapse; width: 100%; font-size: 10pt; }"
        "th, td { border: 1px solid #d0d7de; padding: 4px 6px; text-align: left; }"
        "code { font-family: Courier, monospace; font-size: 10pt; }"
        "pre { white-space: pre-wrap; font-size: 9pt; background: #f6f8fa; padding: 6px; }"
        "</style></head><body>"
        f"<table width='100%' cellpadding='10' style='background-color:{_MTP_BLUE}'>"
        "<tr><td style='color:#ffffff'>"
        "<span style='font-size:9pt;letter-spacing:2px'>MNEMO &middot; RELEASE ASSURANCE</span>"
        "<br/><span style='font-size:17pt;font-weight:bold'>Acta de aseguramiento de QA</span>"
        "</td></tr></table>"
        f"<p><strong>Evaluación del motor:</strong> <span class='verdict' style='color:{color}'>{_e(verdict)}</span>"
        f" &middot; <strong>Risk score:</strong> {risk_html}</p>"
        f"{sin_confirmar_note}"
        f"<p>Proyecto <code>{_e(idn.get('project'))}</code> &middot; commit <code>{_e(idn.get('commit_sha'))}</code>"
        f" &middot; run <code>{_e(idn.get('run_id'))}</code> &middot; {_e(idn.get('created_at'))}</p>"
        f"<p>Mnemo {_e(idn.get('mnemo_version'))} &middot; modelo {_e(idn.get('model_version'))}</p>"
        f"{manifest_html}"
        f"{disclaimer_html}"
        f"<p><strong>Desglose:</strong> {breakdown}</p>"
        f"{self_eval_html}"
        "<h2>Evidencia</h2><table border='1' cellpadding='4'>"
        "<tr><th>failure_id</th><th>categoría</th><th>confianza</th><th>regla</th><th>req. aprobación</th></tr>"
        f"{rows}</table>"
        f"<h2>Firma (Ed25519)</h2><pre style='white-space:pre-wrap'>{_e(signature)}</pre>"
        f"{firma_html}{verificable}"
        "</body></html>"
    )


def render_pdf(cert: Dict[str, Any], signature: str, public_url: str = "") -> bytes:
    from xhtml2pdf import pisa  # import local: solo se carga al generar PDF
    html = render_html(cert, signature, public_url)
    buffer = BytesIO()
    status = pisa.CreatePDF(html, dest=buffer)
    if status.err:
        raise RuntimeError("No se pudo generar el PDF del certificado")
    return buffer.getvalue()
