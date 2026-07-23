"""Import de conocimiento desde Atlassian a la bandeja de propuestas.

Determinista por diseño: el LLM NO participa aquí (vive en el refine por-propuesta).
La URL externa se DERIVA del base_url configurado — jamás del texto pegado
(SSRF/phishing): del input solo se aceptan claves validadas con regex estricta.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.jira.client import JiraApiClient, JiraApiError
from src.jira.models import JiraIssue
from src.jira.safe_url import validate_base_url
from src.sanitizer import sanitize_text

_JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
_CONFLUENCE_URL_RE = re.compile(r"https?://\S*/pages/\d+")
_MAX_REFS = 10
_MAX_IMPORTS_PER_HOUR = 30
_FETCH_WORKERS = 4


class ImportNotConfigured(Exception):
    """No hay integración Atlassian configurada para la org."""


class ImportRateLimited(Exception):
    """Tope de imports/hora de la org alcanzado."""


@dataclass(frozen=True)
class ParsedRef:
    source: str        # 'jira' (PR2 añade 'confluence')
    key: str           # 'PAY-123'
    external_ref: str  # 'jira:PAY-123'


@dataclass(frozen=True)
class RefError:
    ref: str
    reason: str


def parse_refs(refs: List[str]) -> Tuple[List[ParsedRef], List[RefError]]:
    """Valida cada ref con regex ESTRICTA (nunca se interpola texto crudo en un path
    de la API). Dedupe silencioso; vacías se ignoran; el resto → error por-ref."""
    parsed: List[ParsedRef] = []
    errors: List[RefError] = []
    seen: set = set()
    for raw in refs:
        ref = (raw or "").strip()
        if not ref:
            continue
        if _JIRA_KEY_RE.match(ref):
            if ref in seen:
                continue
            seen.add(ref)
            parsed.append(ParsedRef(source="jira", key=ref, external_ref=f"jira:{ref}"))
        elif _CONFLUENCE_URL_RE.match(ref):
            errors.append(RefError(
                ref=ref, reason="Las páginas de Confluence llegan en la siguiente versión."))
        else:
            errors.append(RefError(
                ref=ref, reason="No parece una clave de Jira (formato PROJ-123)."))
    return parsed, errors


def _draft_from_issue(issue: JiraIssue, base_url: str) -> Dict[str, Any]:
    key = issue.key
    project = key.split("-")[0]
    outcome = None
    if issue.resolution:
        fecha = issue.resolution_date[:10] if issue.resolution_date else ""
        outcome = f"Resolución: {issue.resolution}" + (f" ({fecha})" if fecha else "")
    return {
        "kind": "leccion",
        "title": sanitize_text(issue.summary)[:300] or key,
        "challenge": (sanitize_text(issue.description)[:4000] or None),
        # Los criterios de aceptación son el "cómo debe comportarse" → approach,
        # que SÍ entra en el embedding (embedding_text usa title/challenge/approach).
        "approach": (sanitize_text(issue.acceptance_criteria)[:4000] or None),
        "outcome": outcome,
        "domain": None,
        "tags": [project],
        "project": project,
        "external_url": f"{base_url.rstrip('/')}/browse/{key}",
    }


class KnowledgeImportService:
    def __init__(self, *, repo, integrations,
                 client_factory: Optional[Callable[[Dict[str, Any]], Any]] = None):
        self.repo = repo                  # KnowledgeProposalRepository
        self.integrations = integrations  # IntegrationsRepository
        # Un cliente POR HILO (requests.Session no es thread-safe) → factory.
        self._client_factory = client_factory or (
            lambda creds: JiraApiClient(creds["base_url"], creds["email"],
                                        creds["token"], timeout=10))

    def import_refs(self, *, user_id: str, org_id: str,
                    refs: List[str]) -> Dict[str, Any]:
        if len(refs) > _MAX_REFS:
            raise ValueError(f"máximo {_MAX_REFS} referencias por tanda")
        creds = self.integrations.get_jira_credentials(user_id=user_id, org_id=org_id)
        if creds is None:
            raise ImportNotConfigured(
                "Configura la integración de Jira en Integraciones antes de importar.")
        validate_base_url(creds["base_url"])  # re-validación en el momento del uso (TOCTOU)
        parsed, errors = parse_refs(refs)
        recent = self.repo.count_recent_imports(user_id=user_id, org_id=org_id)
        if recent + len(parsed) > _MAX_IMPORTS_PER_HOUR:
            raise ImportRateLimited(
                f"Tope de {_MAX_IMPORTS_PER_HOUR} imports/hora de la organización alcanzado."
                " Inténtalo más tarde.")

        def fetch(p: ParsedRef):
            client = self._client_factory(creds)
            return client.fetch_issue(p.key)

        created: List[Dict[str, Any]] = []
        refreshed: List[Dict[str, Any]] = []
        skipped: List[str] = []
        with ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
            futures = [(p, pool.submit(fetch, p)) for p in parsed]
            for p, fut in futures:
                try:
                    issue = fut.result()
                except JiraApiError as exc:
                    errors.append(RefError(ref=p.key, reason=f"Jira: {exc}"))
                    continue
                draft = _draft_from_issue(issue, creds["base_url"])
                row = self.repo.upsert_import_proposal(
                    user_id=user_id, org_id=org_id, created_by=user_id,
                    source=p.source, external_ref=p.external_ref, **draft)
                if row is None:
                    skipped.append(p.key)      # ya aprobada/rechazada (o no-miembro)
                elif row.get("created"):
                    created.append(row)
                else:
                    refreshed.append(row)
        return {"created": created, "refreshed": refreshed, "skipped": skipped,
                "errors": [{"ref": e.ref, "reason": e.reason} for e in errors]}
