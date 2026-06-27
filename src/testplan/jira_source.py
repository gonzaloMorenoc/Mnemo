"""Ingesta de Historias de Usuario (HU) desde una URL de issue de Jira.

Uso típico:
    text = hu_text_from_jira(
        url="https://acme.atlassian.net/browse/DIA-1234",
        org_id="org-uuid",
        user_id="user-uuid",
        repo=integrations_repo,
    )
"""
import re
from typing import Any

from src.jira.client import JiraApiClient

# Patrón que captura claves tipo PROJECT-123 o MYAPP-456 en URLs de Jira.
# Soporta dos formas:
#   /browse/KEY-123
#   ?selectedIssue=KEY-123  (vista de backlog/tablero)
_BROWSE_RE = re.compile(r"/browse/([A-Z][A-Z0-9]+-\d+)")
_SELECTED_RE = re.compile(r"[?&]selectedIssue=([A-Z][A-Z0-9]+-\d+)")


def parse_issue_key(url: str) -> str:
    """Extrae la clave de issue de una URL de Jira.

    Soporta:
      - https://x.atlassian.net/browse/KEY-123
      - https://x.atlassian.net/...?selectedIssue=KEY-123

    Lanza ``ValueError`` si no se encuentra ninguna clave.
    """
    for pattern in (_BROWSE_RE, _SELECTED_RE):
        m = pattern.search(url)
        if m:
            return m.group(1)
    raise ValueError(f"No se encontró una key de issue de Jira en la URL: {url!r}")


def hu_text_from_jira(
    *,
    url: str,
    org_id: str,
    user_id: str,
    repo: Any,
) -> str:
    """Obtiene el texto de una HU a partir de una URL de Jira.

    1. Parsea la clave del issue desde la URL.
    2. Carga las credenciales Jira del org vía ``repo.get_jira_credentials``.
    3. Instancia ``JiraApiClient`` y llama a ``fetch_issue``.
    4. Compone y devuelve un texto con summary, description y criterios de
       aceptación (si están presentes).

    Args:
        url: URL de Jira del issue (``/browse/KEY-123`` o ``?selectedIssue=KEY-123``).
        org_id: Identificador de la organización.
        user_id: Identificador del usuario que realiza la solicitud (para autorización).
        repo: Instancia de ``IntegrationsRepository`` (o compatible).

    Returns:
        Texto plano con la HU lista para ser procesada por el agente de plan de pruebas.

    Raises:
        ValueError: Si la URL no contiene una clave válida o si el org no tiene
                    configurada la integración de Jira.
    """
    key = parse_issue_key(url)

    creds = repo.get_jira_credentials(user_id=user_id, org_id=org_id)
    if creds is None:
        raise ValueError(
            "La organización no tiene configurada la integración de Jira. "
            "Configúrala en Ajustes → Integraciones."
        )

    client = JiraApiClient(
        base_url=creds["base_url"],
        email=creds["email"],
        token=creds["token"],
    )
    issue = client.fetch_issue(key)

    parts = [f"# {issue.summary}"]
    if issue.description:
        parts.append(issue.description)
    if issue.acceptance_criteria:
        parts.append(f"## Criterios de aceptación\n{issue.acceptance_criteria}")

    return "\n\n".join(parts)
