"""Cliente de Confluence Cloud — misma dependencia (atlassian-python-api) y mismas
credenciales de cuenta Atlassian que la integración Jira (el token es de cuenta,
no de producto): base_url + "/wiki".

Solo Cloud (cloud=True), igual que el resto de la integración Atlassian.
"""
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

from atlassian import Confluence


class ConfluenceApiError(Exception):
    """Error al hablar con la API de Confluence (red, auth, sin licencia, 404…)."""


@dataclass(frozen=True)
class ParsedPage:
    page_id: str
    space_key: str


@dataclass(frozen=True)
class ConfluencePage:
    id: str
    title: str
    text: str
    space_key: str


_PAGE_ID_RE = re.compile(r"/pages/(\d+)(?:/|$)")
_SPACE_RE = re.compile(r"/spaces/([^/]+)/")


def parse_confluence_url(url: str, configured_base_url: str) -> "ParsedPage | None":
    """Extrae el pageId de una URL de Confluence SOLO si su host coincide con el
    base_url configurado (pegar una página de otro site importaría en silencio la
    página con ese mismo id numérico del site propio → contenido equivocado).
    Del texto pegado solo sobrevive el pageId numérico — jamás se usa como host."""
    try:
        pasted = urlparse(url.strip())
        configured = urlparse(configured_base_url.strip())
    except ValueError:
        return None
    if not pasted.hostname or pasted.hostname != configured.hostname:
        return None
    m = _PAGE_ID_RE.search(pasted.path)
    if not m:
        return None
    space = _SPACE_RE.search(pasted.path)
    return ParsedPage(page_id=m.group(1), space_key=space.group(1) if space else "")


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style"}
    # Los tags inline no separan palabras ("Hola <b>mundo</b>." debe dar "Hola mundo.")
    _INLINE = {"a", "b", "code", "em", "i", "s", "span", "strong", "sub", "sup", "u"}

    def __init__(self):
        super().__init__()
        self._chunks: list = []
        self._skip_depth = 0

    def _separator(self, tag):
        if tag not in self._INLINE and tag not in self._SKIP:
            self._chunks.append(" ")

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        self._separator(tag)

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        self._separator(tag)

    def handle_data(self, data):
        if not self._skip_depth:
            self._chunks.append(data)


def html_to_text(html: str) -> str:
    """HTML (formato storage de Confluence) → texto plano con whitespace colapsado.
    Stdlib html.parser: sin dependencias nuevas."""
    extractor = _TextExtractor()
    extractor.feed(html or "")
    return re.sub(r"\s+", " ", "".join(extractor._chunks)).strip()


class ConfluenceApiClient:
    def __init__(self, base_url: str, email: str, token: str, timeout: int = 10):
        # timeout explícito por la misma razón que el cliente Jira: el default de
        # la librería (75 s) es mayor que los 55 s del proxy del frontend.
        self._confluence = Confluence(url=f"{base_url.rstrip('/')}/wiki",
                                      username=email, password=token, cloud=True,
                                      timeout=timeout)

    def fetch_page(self, page_id: str) -> ConfluencePage:
        try:
            raw = self._confluence.get_page_by_id(page_id, expand="body.storage,space")
        except Exception as exc:  # noqa: BLE001 — envolvemos cualquier fallo (incl. 404 sin licencia)
            raise ConfluenceApiError(str(exc)) from exc
        body = (((raw or {}).get("body") or {}).get("storage") or {}).get("value") or ""
        return ConfluencePage(
            id=str((raw or {}).get("id") or page_id),
            title=((raw or {}).get("title") or "").strip(),
            text=html_to_text(body),
            space_key=((raw or {}).get("space") or {}).get("key") or "",
        )
