import re
from typing import Optional, Set

# Clasificación heurística del error. Categorías NO excluyentes: un mensaje puede
# casar varias; el motor (engine) resuelve la prioridad. Cap de longitud como
# defensa frente a mensajes enormes. Alternaciones lineales (sin backtracking).

_INFRA = re.compile(
    r"ECONNREFUSED|ECONNRESET|ETIMEDOUT|EAI_AGAIN|net::ERR|socket hang up|"
    r"getaddrinfo|connection refused|target[^\n]{0,80}closed|"
    r"browser has been closed|page crashed|browser[^\n]{0,40}crash",
    re.IGNORECASE,
)
_LOCATOR = re.compile(
    r"waiting for selector|waiting for locator|waiting for get_?by|get_?by[a-z_]*\(|"
    r"strict mode violation|resolved to 0 elements|no node found|locator not found|"
    r"element is not (visible|attached|enabled|editable|stable)|"
    r"expected to be (visible|attached|enabled|checked|editable|in viewport)",
    re.IGNORECASE,
)
_ASSERTION = re.compile(
    r"expect\(|assertionerror|(?:^|\n)[ \t]*expected:|(?:^|\n)[ \t]*received:",
    re.IGNORECASE,
)


def classify_error(error_type: Optional[str], message: str, trace: Optional[str] = None) -> Set[str]:
    """Clasifica un error en {'infra','locator','assertion'} (no excluyente),
    combinando error_type + message + trace (donde Playwright deja el call log)."""
    text = f"{error_type or ''}\n{message or ''}\n{trace or ''}"[:50000]
    cats: Set[str] = set()
    if _INFRA.search(text):
        cats.add("infra")
    if _LOCATOR.search(text):
        cats.add("locator")
    if _ASSERTION.search(text):
        cats.add("assertion")
    return cats
