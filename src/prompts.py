import re
import json
from langchain_core.prompts import PromptTemplate

# ── Structured output prompt ──────────────────────────────────────────────────
# Instructs the model to return a single valid JSON object.
# DeepSeek-R1 wraps its reasoning in <thought>…</thought> before the JSON;
# parse_analysis_json() strips those tags before parsing.
QA_ENGINEER_TEMPLATE = """Eres un QA Automation Engineer experto en debugging.
Analiza el siguiente error usando los fragmentos de logs históricos y soluciones
previas como contexto.

CONTEXTO DE ERRORES PREVIOS:
{context}

NUEVO ERROR A ANALIZAR:
{question}

Responde ÚNICAMENTE con un objeto JSON válido con esta estructura exacta
(sin texto antes ni después del JSON):
{{
  "root_cause": "descripción concisa de la causa raíz en 1-2 frases",
  "severity": "critical|high|medium|low",
  "confidence": "high|medium|low",
  "investigation_steps": [
    "paso concreto de investigación 1",
    "paso concreto de investigación 2"
  ],
  "suggested_fix": "solución concreta; incluye código o comandos si es relevante"
}}

Reglas:
- severity: critical=sistema caído/bloqueante, high=fallo frecuente, medium=degradación, low=cosmético
- confidence: high=solución en contexto, medium=similar en contexto, low=inferido/sin contexto
- Si no hay solución en el contexto, usa confidence="low" y sugiere pasos generales
- investigation_steps: mínimo 2, máximo 5 pasos accionables
"""

PROMPT = PromptTemplate(
    template=QA_ENGINEER_TEMPLATE,
    input_variables=["context", "question"]
)

_REQUIRED_KEYS = {"root_cause", "severity", "confidence", "investigation_steps", "suggested_fix"}
_VALID_SEVERITIES = {"critical", "high", "medium", "low"}
_VALID_CONFIDENCES = {"high", "medium", "low"}


def parse_analysis_json(raw: str) -> dict | None:
    """Extracts and validates the JSON block from a (possibly <thought>-wrapped) response.

    Returns a dict with the 5 required keys, or None if parsing fails.
    The caller should fall back to displaying the raw text when None is returned.
    """
    # Strip DeepSeek reasoning block
    text = raw
    if "</thought>" in raw:
        text = raw.split("</thought>", 1)[1]

    # Find the outermost JSON object (handles leading/trailing whitespace or text)
    match = re.search(r'\{[\s\S]*\}', text.strip())
    if not match:
        return None

    try:
        parsed = json.loads(match.group())
    except (json.JSONDecodeError, ValueError):
        return None

    # Validate structure
    if not _REQUIRED_KEYS.issubset(parsed.keys()):
        return None
    if parsed.get("severity") not in _VALID_SEVERITIES:
        parsed["severity"] = "medium"
    if parsed.get("confidence") not in _VALID_CONFIDENCES:
        parsed["confidence"] = "low"
    if not isinstance(parsed.get("investigation_steps"), list):
        return None

    return parsed
