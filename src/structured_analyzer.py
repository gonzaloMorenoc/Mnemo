import json
from typing import Any, Dict, List

from langchain_ollama import OllamaLLM

from src.config import MODEL_NAME, OLLAMA_BASE_URL


ANALYSIS_PROMPT_TEMPLATE = """
You are TraceFix, an expert QA/SRE debugging assistant.
Use only the supplied context snippets to explain and fix the error.
If context is insufficient, explicitly say so.

Return ONLY valid JSON with this exact schema:
{{
  "root_cause": "string",
  "why_it_happened": "string",
  "how_to_fix": "string",
  "suggested_patch_steps": ["step1", "step2"],
  "confidence": 0.0
}}

Question:
{error_log}

Context snippets:
{context_block}
"""


class StructuredAnalyzer:
    def __init__(self, model_name: str = MODEL_NAME):
        self.llm = OllamaLLM(model=model_name, base_url=OLLAMA_BASE_URL)

    def _build_context_block(self, contexts: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for item in contexts:
            scope = item.get("scope", "unknown")
            title = item.get("source_title", "unknown")
            content = item.get("content", "")
            lines.append(f"[{scope} | {title}] {content}")
        return "\n\n".join(lines[:10])

    def _fallback_response(self) -> Dict[str, Any]:
        return {
            "root_cause": "Insufficient context to identify a single root cause.",
            "why_it_happened": "The available snippets are not enough to conclude with high confidence.",
            "how_to_fix": "Collect more logs, stack traces, and the exact failing test context.",
            "suggested_patch_steps": [
                "Capture full stack trace and failing test name",
                "Re-run with debug logging enabled",
                "Correlate with latest code/config changes",
            ],
            "confidence": 0.2,
        }

    def analyze(self, *, error_log: str, contexts: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not contexts:
            return self._fallback_response()

        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            error_log=error_log.strip(),
            context_block=self._build_context_block(contexts),
        )
        raw = self.llm.invoke(prompt)
        if isinstance(raw, dict):
            raw = raw.get("text", "") or raw.get("output_text", "")
        if not isinstance(raw, str):
            return self._fallback_response()

        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return self._fallback_response()

        try:
            payload = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return self._fallback_response()

        payload.setdefault("root_cause", "")
        payload.setdefault("why_it_happened", "")
        payload.setdefault("how_to_fix", "")
        payload.setdefault("suggested_patch_steps", [])
        payload.setdefault("confidence", 0.0)

        if not isinstance(payload["suggested_patch_steps"], list):
            payload["suggested_patch_steps"] = [str(payload["suggested_patch_steps"])]
        try:
            payload["confidence"] = float(payload["confidence"])
        except (TypeError, ValueError):
            payload["confidence"] = 0.0
        payload["confidence"] = max(0.0, min(1.0, payload["confidence"]))

        return payload
