"""Import de conocimiento desde Atlassian a la bandeja de propuestas.

Determinista por diseño: el LLM NO participa aquí (vive en el refine por-propuesta).
La URL externa se DERIVA del base_url configurado — jamás del texto pegado
(SSRF/phishing): del input solo se aceptan claves validadas con regex estricta.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.confluence.client import (
    ConfluenceApiClient,
    ConfluenceApiError,
    ConfluencePage,
    parse_confluence_url,
)
from src.jira.client import JiraApiClient, JiraApiError
from src.jira.models import JiraIssue
from src.jira.safe_url import validate_base_url
from src.knowledge.sectioning import section_drafts
from src.sanitizer import sanitize_text

_JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
_CONFLUENCE_URL_RE = re.compile(r"https?://\S*/pages/\d+")
_MAX_REFS = 10
# SECCIONES por hora y org (antes: 30 páginas). Al pasar a contar secciones, 30 serían
# ~2-3 páginas reales por hora — imposible heredar la wiki de un proyecto. 60 sigue
# frenando el abuso sin convertir el caso de uso principal en un goteo.
_MAX_IMPORTS_PER_HOUR = 60
_FETCH_WORKERS = 4


class ImportNotConfigured(Exception):
    """No hay integración Atlassian configurada para la org."""


class ImportRateLimited(Exception):
    """Tope de imports/hora de la org alcanzado."""


@dataclass(frozen=True)
class ParsedRef:
    source: str        # 'jira' | 'confluence'
    key: str           # 'PAY-123' | pageId ('12345')
    external_ref: str  # 'jira:PAY-123' | 'confluence:12345'
    space_key: str = ""  # solo confluence (para tags)


@dataclass(frozen=True)
class RefError:
    ref: str
    reason: str


def parse_refs(refs: List[str],
               configured_base_url: str) -> Tuple[List[ParsedRef], List[RefError]]:
    """Valida cada ref con regex ESTRICTA (nunca se interpola texto crudo en un path
    de la API). URLs de Confluence: solo del site CONFIGURADO — el host pegado jamás
    se usa, y una URL de otro site sería contenido equivocado, no un fetch a otro
    host. Dedupe silencioso; vacías se ignoran; el resto → error por-ref."""
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
            page = parse_confluence_url(ref, configured_base_url)
            if page is None:
                errors.append(RefError(
                    ref=ref,
                    reason="La URL no pertenece a tu site de Atlassian configurado"
                           " (otro site) o no es una página de Confluence."))
                continue
            if page.page_id in seen:
                continue
            seen.add(page.page_id)
            parsed.append(ParsedRef(source="confluence", key=page.page_id,
                                    external_ref=f"confluence:{page.page_id}",
                                    space_key=page.space_key))
        else:
            errors.append(RefError(
                ref=ref,
                reason="No parece una clave de Jira (PROJ-123) ni una URL de"
                       " página de Confluence."))
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


def _draft_from_section(page: ConfluencePage, ref: ParsedRef, base_url: str,
                        draft: Dict[str, Any]) -> Dict[str, Any]:
    """Una sección de una página → borrador de propuesta.

    `sanitize_text` se aplica POR SECCIÓN: su cota interna son 20.000 caracteres, así
    que saneando la página entera la cola de un documento largo se quedaría sin
    redactar (emails, tokens). El cap por sección ya lo aplicó section_drafts.
    """
    space = page.space_key or ref.space_key
    return {
        "kind": "leccion",  # el kind lo decide el curador en la bandeja (aquí no hay LLM)
        "title": sanitize_text(draft["title"])[:300] or f"Página {ref.key}",
        # El texto de la sección es el "qué hay que saber" → challenge (entra en el
        # embedding); destilarlo en approach/outcome es trabajo del refine/curador.
        "challenge": sanitize_text(draft["body"]) or None,
        "approach": None,
        "outcome": None,
        "domain": None,
        "tags": [space] if space else [],
        "project": None,
        "external_url": f"{base_url.rstrip('/')}/wiki/pages/viewpage.action?pageId={ref.key}",
    }


def _clasificar(row: Optional[Dict[str, Any]], key: str, created: List[Dict[str, Any]],
                refreshed: List[Dict[str, Any]], skipped: List[str]) -> None:
    """Reparte el resultado de un upsert en los tres cubos de la respuesta.

    row None = la propuesta ya estaba aprobada/rechazada (o no es miembro): no
    resucita. `created` lo marca el xmax=0 del upsert."""
    if row is None:
        skipped.append(key)
    elif row.get("created"):
        created.append(row)
    else:
        refreshed.append(row)


class KnowledgeImportService:
    def __init__(self, *, repo, integrations,
                 client_factory: Optional[Callable[[Dict[str, Any]], Any]] = None,
                 confluence_client_factory: Optional[Callable[[Dict[str, Any]], Any]] = None):
        self.repo = repo                  # KnowledgeProposalRepository
        self.integrations = integrations  # IntegrationsRepository
        # Un cliente POR HILO (requests.Session no es thread-safe) → factories.
        self._client_factory = client_factory or (
            lambda creds: JiraApiClient(creds["base_url"], creds["email"],
                                        creds["token"], timeout=10))
        self._confluence_client_factory = confluence_client_factory or (
            lambda creds: ConfluenceApiClient(creds["base_url"], creds["email"],
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
        parsed, errors = parse_refs(refs, creds["base_url"])
        recent = self.repo.count_recent_imports(user_id=user_id, org_id=org_id)
        if recent + len(parsed) > _MAX_IMPORTS_PER_HOUR:
            raise ImportRateLimited(
                f"Tope de {_MAX_IMPORTS_PER_HOUR} imports/hora de la organización alcanzado."
                " Inténtalo más tarde.")

        def fetch(p: ParsedRef):
            if p.source == "confluence":
                return self._confluence_client_factory(creds).fetch_page(p.key)
            return self._client_factory(creds).fetch_issue(p.key)

        created: List[Dict[str, Any]] = []
        refreshed: List[Dict[str, Any]] = []
        skipped: List[str] = []
        skipped_sections: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
            futures = [(p, pool.submit(fetch, p)) for p in parsed]
            for p, fut in futures:
                try:
                    content = fut.result()
                except JiraApiError as exc:
                    errors.append(RefError(ref=p.key, reason=f"Jira: {exc}"))
                    continue
                except ConfluenceApiError as exc:
                    errors.append(RefError(ref=p.key, reason=f"Confluence: {exc}"))
                    continue
                if p.source == "confluence":
                    self._import_page(user_id=user_id, org_id=org_id, ref=p,
                                      page=content, base_url=creds["base_url"],
                                      created=created, refreshed=refreshed,
                                      skipped=skipped, skipped_sections=skipped_sections)
                    continue
                draft = _draft_from_issue(content, creds["base_url"])
                row = self.repo.upsert_import_proposal(
                    user_id=user_id, org_id=org_id, created_by=user_id,
                    source=p.source, external_ref=p.external_ref, **draft)
                _clasificar(row, p.key, created, refreshed, skipped)
        return {"created": created, "refreshed": refreshed, "skipped": skipped,
                "skipped_sections": skipped_sections,
                "errors": [{"ref": e.ref, "reason": e.reason} for e in errors]}

    def _import_page(self, *, user_id: str, org_id: str, ref: ParsedRef,
                     page: ConfluencePage, base_url: str,
                     created: List[Dict[str, Any]], refreshed: List[Dict[str, Any]],
                     skipped: List[str], skipped_sections: List[Dict[str, Any]]) -> None:
        """Importa UNA página de Confluence como una propuesta por sección.

        Transición desde los imports anteriores al seccionado, cuyo external_ref era
        la página entera: si el humano ya decidió sobre ella (aprobada o rechazada) no
        la resucitamos troceada; si solo estaba pendiente, su versión truncada se borra
        y la sustituyen las secciones.
        """
        estado = self.repo.page_ref_status(
            user_id=user_id, org_id=org_id, external_ref=ref.external_ref)
        if estado in ("rejected", "approved"):
            skipped.append(ref.key)
            return
        if estado == "pending":
            self.repo.delete_pending_by_ref(
                user_id=user_id, org_id=org_id, external_ref=ref.external_ref)

        drafts, descartadas = section_drafts(page.title, page.sections)
        # El pre-check contó PÁGINAS (las secciones aún no se conocían: hay que
        # traerlas de la red primero). El cupo de verdad se aplica aquí, en secciones.
        caben = max(0, _MAX_IMPORTS_PER_HOUR - self.repo.count_recent_imports(
            user_id=user_id, org_id=org_id))
        if len(drafts) > caben:
            descartadas += len(drafts) - caben
            drafts = drafts[:caben]
        if descartadas:
            skipped_sections.append({"ref": ref.key, "descartadas": descartadas})

        for d in drafts:
            draft = _draft_from_section(page, ref, base_url, d)
            row = self.repo.upsert_import_proposal(
                user_id=user_id, org_id=org_id, created_by=user_id,
                source=ref.source, external_ref=f"{ref.external_ref}#{d['slug']}",
                **draft)
            _clasificar(row, ref.key, created, refreshed, skipped)
