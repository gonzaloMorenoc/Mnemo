"""Secciones de una página importada → borradores de propuesta. Puro: sin red ni BD.

Por qué existe: importar una página entera como un solo item la truncaba a 2.000
caracteres (auditoría 12-ago, H4b) y, aunque no se truncara, un único embedding para
un documento largo diluye la señal — justo lo contrario de lo que persigue el paso 1.
La sección es la unidad que el autor ya definió con sus encabezados.
"""
import re
import unicodedata
from typing import Any, Dict, List, Sequence, Tuple

MAX_SECTIONS = 12         # por página: acota el peor caso de la bandeja de propuestas
MAX_SECTION_CHARS = 4000  # = max_length de challenge en el approve (multitenant_models)
TRUNCATION_MARK = "… [contenido truncado — ver original]"

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Encabezado → fragmento estable para el external_ref.

    Se usa el slug y no la posición porque reordenar la página cambiaría todos los
    índices y duplicaría la bandeja entera. Renombrar un encabezado sí rompe la
    identidad (la propuesta vieja queda huérfana): limitación asumida.
    """
    normalizado = unicodedata.normalize("NFKD", text or "")
    sin_tildes = "".join(c for c in normalizado if not unicodedata.combining(c))
    slug = _NON_ALNUM.sub("-", sin_tildes.lower()).strip("-")
    return slug or "seccion"


def section_drafts(page_title: str, sections: Sequence[Tuple[str, str]], *,
                   max_sections: int = MAX_SECTIONS,
                   max_chars: int = MAX_SECTION_CHARS) -> Tuple[List[Dict[str, Any]], int]:
    """[(encabezado, texto)] → (drafts, nº de secciones descartadas por el tope).

    El descarte se DEVUELVE para que el llamador lo avise: un tope silencioso se lee
    como "se importó todo" cuando no fue así.
    """
    drafts: List[Dict[str, Any]] = []
    vistos: Dict[str, int] = {}
    for heading, body in sections[:max_sections]:
        if not (body or "").strip():
            continue
        base = slugify(heading)
        vistos[base] = vistos.get(base, 0) + 1
        slug = base if vistos[base] == 1 else f"{base}-{vistos[base]}"
        cuerpo = body if len(body) <= max_chars else body[:max_chars] + TRUNCATION_MARK
        drafts.append({
            "slug": slug,
            "title": f"{page_title} — {heading}" if heading else page_title,
            "body": cuerpo,
        })
    return drafts, max(0, len(sections) - max_sections)
