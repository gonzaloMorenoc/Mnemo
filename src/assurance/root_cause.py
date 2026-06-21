from typing import Any, Dict, List

_MAX_FAILURES = 6


def _top_frame(trace: str) -> str:
    for line in (trace or "").splitlines():
        s = line.strip()
        if s.startswith("at ") or " line " in s or 'File "' in s:
            return s
    return ""


def build_root_cause_prompt(family: Dict[str, Any], failures: List[Dict[str, Any]]) -> str:
    """Construye el prompt de causa raíz (puro, sin LLM)."""
    projects = sorted({f.get("project") for f in failures if f.get("project")})
    lines = []
    for f in failures[:_MAX_FAILURES]:
        lines.append(
            f"- test={f.get('test_name')} tipo={f.get('error_type')} "
            f"msg={(f.get('message') or '')[:300]} frame={_top_frame(f.get('trace'))}"
        )
    samples = "\n".join(lines)
    return (
        "Eres un ingeniero de QA senior. Analiza esta familia de defectos y propon la causa raiz "
        "mas probable y pasos de correccion. SOLO ves sintomas (mensajes y trazas), no el codigo "
        "fuente, asi que tus pasos son heuristicos.\n\n"
        f"Familia: {family.get('title')}\n"
        f"Ocurrencias: {family.get('occurrence_count')} | Proyectos: {', '.join(projects) or 'n/d'}\n"
        f"Muestra de fallos:\n{samples}\n\n"
        "Responde en espanol, en markdown, con exactamente estas dos secciones:\n"
        "## Causa raíz\n(1-3 frases)\n## Pasos sugeridos\n(3-5 pasos numerados)"
    )
