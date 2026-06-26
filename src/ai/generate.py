import json
from typing import Any, Dict, List, Optional


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
        except Exception:  # noqa: BLE001 — sin provider → degrada
            return _fail()
    full = f"{prompt}\n\nContext snippets:\n{_build_context_block(context)}"
    try:
        raw = provider.complete(full)
    except Exception:  # noqa: BLE001 — LLM caído → degrada
        return _fail()
    parsed = _parse_json(raw)
    if parsed is None:
        return _fail()
    out = {k: v for k, v in schema.items()}
    for k in schema:
        if k in parsed:
            out[k] = parsed[k]
    return out
