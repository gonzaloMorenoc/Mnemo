from dataclasses import dataclass
from typing import Any


@dataclass
class JiraBug:
    key: str
    summary: str
    description: str
    issue_type: str
    status: str
    url: str = ""


def adf_to_text(value: Any) -> str:
    """Aplana una descripción de Jira: ADF (dict) → texto plano; str → str; None → ''."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text" and isinstance(node.get("text"), str):
                parts.append(node["text"])
            for child in node.get("content") or []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return " ".join(parts).strip()
