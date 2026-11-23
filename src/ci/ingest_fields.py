"""Validación de los campos multipart opcionales de la ingesta por token.

`commit_sha` llega del CI (p. ej. `$GITHUB_SHA`) y acaba en el manifiesto firmado,
en `test_runs.commit_sha` (lo usa el gate para publicar el check en GitHub) y en la
señal `intermittent_same_sha` del triaje. `branch` solo entra en el manifiesto.
Se validan en la frontera: nunca se confía en lo que manda el cliente.
"""
import re
from typing import Optional

COMMIT_SHA_MIN_LEN = 7
COMMIT_SHA_MAX_LEN = 40
BRANCH_MAX_LEN = 255
PROJECT_MAX_LEN = 200

_COMMIT_SHA_RE = re.compile(
    rf"^[0-9a-f]{{{COMMIT_SHA_MIN_LEN},{COMMIT_SHA_MAX_LEN}}}$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def parse_commit_sha(raw: Optional[str]) -> Optional[str]:
    """SHA de git en hexadecimal (7-40), normalizado a minúsculas; None si no viene.
    Lanza ValueError si viene con otro formato."""
    value = (raw or "").strip().lower()
    if not value:
        return None
    if not _COMMIT_SHA_RE.match(value):
        raise ValueError(
            f"commit_sha inválido: se espera un SHA de git en hexadecimal "
            f"({COMMIT_SHA_MIN_LEN}-{COMMIT_SHA_MAX_LEN} caracteres)")
    return value


def parse_branch(raw: Optional[str]) -> Optional[str]:
    """Nombre de rama acotado y sin caracteres de control; None si no viene."""
    value = (raw or "").strip()
    if not value:
        return None
    if len(value) > BRANCH_MAX_LEN:
        raise ValueError(f"branch demasiado largo (máx. {BRANCH_MAX_LEN})")
    if _CONTROL_CHARS_RE.search(value):
        raise ValueError("branch contiene caracteres de control")
    return value


def optional_text(value) -> Optional[str]:
    """Campo de formulario de texto opcional (un archivo en su lugar cuenta como ausente)."""
    return value if isinstance(value, str) else None
