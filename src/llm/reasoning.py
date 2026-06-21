import re

_THINK_OPEN_TAG = re.compile(r"<think>", re.IGNORECASE)
_THINK_CLOSE_TAG = re.compile(r"</think>", re.IGNORECASE)
_THINK_GREEDY_RE = re.compile(r"<think>.*</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think>.*\Z", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Elimina bloques <think>...</think> (incl. anidados y uno sin cerrar al final).

    Cuando hay más etiquetas de apertura que de cierre (i.e. existe un <think>
    sin cerrar), elimina todo desde el primer <think> hasta el final de la cadena.
    De lo contrario, elimina cada par cerrado con coincidencia greedy para
    manejar etiquetas anidadas correctamente.
    """
    if not text:
        return text
    opens = len(_THINK_OPEN_TAG.findall(text))
    if opens == 0:
        return text.strip()
    closes = len(_THINK_CLOSE_TAG.findall(text))
    if opens > closes:
        # Hay un <think> sin cierre — eliminar desde el primero hasta el final,
        # luego limpiar cualquier par cerrado que quedara antes.
        result = _THINK_OPEN_RE.sub("", text)
        result = _THINK_GREEDY_RE.sub("", result)
    else:
        # Todos los opens tienen cierre — greedy remove para manejar nesting.
        result = _THINK_GREEDY_RE.sub("", text)
    return result.strip()
