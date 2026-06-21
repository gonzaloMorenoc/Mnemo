import re

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Elimina bloques <think>...</think> (modelos de razonamiento) del texto."""
    if not text:
        return text
    return _THINK_RE.sub("", text).strip()
