import re
from typing import Optional

_WS = re.compile(r"\s+")


def normalize_dom(html: str) -> str:
    """Normaliza un DOM para comparar de forma robusta: colapsa secuencias de
    espacios en blanco a un solo espacio y recorta los extremos. Coarse pero
    suficiente para la señal 'DOM cambió' (el diff a nivel de elemento es F3)."""
    return _WS.sub(" ", html or "").strip()


def dom_changed(failure_html: Optional[str], green_html: Optional[str]) -> bool:
    """True si el DOM de fallo difiere (normalizado) del último verde. Si falta
    cualquiera de los dos, no hay señal de cambio → False."""
    if not failure_html or not green_html:
        return False
    return normalize_dom(failure_html) != normalize_dom(green_html)
