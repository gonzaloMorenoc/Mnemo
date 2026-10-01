import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _build_context_block(context: List[Dict[str, Any]]) -> str:
    lines = []
    for item in context:
        cid = item.get("id", "?")
        content = item.get("content", "")
        lines.append(f"[{cid}] {content}")
    return "\n\n".join(lines[:10])


def _parse_json(raw: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw, dict):
        raw = raw.get("text", "") or raw.get("output_text", "")
    if not isinstance(raw, str):
        return None
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _format_instruction(schema: Dict[str, Any]) -> str:
    """Exige el formato al final del prompt. Sin esto, modelos como gpt-oss (Groq)
    responden en prosa y la respuesta, buena, se descarta como no parseable."""
    keys = ", ".join(f'"{k}"' for k in schema)
    texto = ("Devuelve SOLO un objeto JSON válido, sin texto antes ni después ni bloques "
             f"de código, con exactamente estas claves: {keys}.")
    if "citations" in schema:
        texto += " Los ids citados van en \"citations\", no dentro del texto."
    return texto


def generate_structured(*, prompt: str, context: List[Dict[str, Any]], schema: Dict[str, Any],
                        provider=None, on_failure: str = "fallback") -> Optional[Dict[str, Any]]:
    """Genera JSON estructurado con el provider híbrido; degrada según on_failure
    ('fallback' → schema con defaults; 'none' → None) ante cualquier fallo del LLM."""
    def _fail():
        return None if on_failure == "none" else {k: v for k, v in schema.items()}

    if provider is None:
        try:
            from src.llm.factory import get_llm_provider
            provider = get_llm_provider()
        except Exception as exc:  # noqa: BLE001 — sin provider → degrada, pero se loguea
            logger.warning("LLM no configurado (generate_structured degrada): %s", exc)
            return _fail()
    full = (f"{prompt}\n\nContext snippets:\n{_build_context_block(context)}"
            f"\n\n{_format_instruction(schema)}")
    try:
        raw = provider.complete(full)
    except Exception as exc:  # noqa: BLE001 — LLM caído → degrada, pero se loguea
        logger.warning("LLM no alcanzable (generate_structured degrada): %r", exc)
        return _fail()
    parsed = _parse_json(raw)
    if parsed is None:
        return _fail()
    out = {k: v for k, v in schema.items()}
    for k in schema:
        if k in parsed:
            out[k] = parsed[k]
    return out
