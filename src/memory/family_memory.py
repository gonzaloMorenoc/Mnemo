"""`FamilyMemory`: lo que el equipo dejó escrito sobre una familia de defectos.

Determinista y sin LLM: etiqueta humana + su razón (quién y cuándo), lecciones
enlazadas y dónde más ha aparecido. Se usa en el check del PR, en la respuesta del
CI, en el panel de triaje y en el ticket propuesto. Es SOLO presentación: no entra
en el veredicto ni en lo firmado.

El texto sale de Mnemo (GitHub, logs del CI), así que todo lo que escribió una persona
se sanea (secretos) y se neutraliza para Markdown (menciones, HTML) al renderizar.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Etiquetas humanas (009_triage.sql) en lenguaje de quien lee el PR.
LABEL_TEXT = {
    "flaky": "intermitente",
    "real": "defecto real",
    "maintenance": "mantenimiento del test",
    "infra": "entorno / infraestructura",
}
UNLABELED = "unknown"

# Solo el conocimiento que ES una lección sobre el fallo. Fuera `dato_prueba` y
# `contacto`: pueden llevar credenciales de entornos o datos de personas que el
# saneado no reconoce («contraseña Qwerty1234!») y esto sale a GitHub y al CI.
LESSON_KINDS = ("leccion", "reto", "patron", "runbook", "decision", "riesgo",
                "regla_negocio", "flujo", "glosario")
MAX_LOAD = 20              # familias que se cargan por run (se muestran MAX_FAMILIES)

MAX_FAMILIES = 5           # por superficie: un PR con 40 fallos no se convierte en un muro
MAX_REASON_CHARS = 400
MAX_LESSON_CHARS = 240
MAX_LESSONS = 3
MAX_MARKDOWN_CHARS = 20_000   # el resumen de un check run admite 65 535


@dataclass(frozen=True)
class Lesson:
    id: str
    kind: str
    title: str
    summary: str


@dataclass(frozen=True)
class FamilyMemory:
    family_id: str
    title: str
    label: Optional[str] = None
    reason: Optional[str] = None
    reason_by: Optional[str] = None
    reason_by_active: bool = True
    reason_by_email: Optional[str] = None   # SOLO para la app (miembros); nunca sale fuera
    reason_at: Optional[str] = None
    lessons: Tuple[Lesson, ...] = field(default_factory=tuple)
    projects: Tuple[str, ...] = field(default_factory=tuple)
    runs: int = 0
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None

    @property
    def has_memory(self) -> bool:
        """¿Hay algo que un humano dejó escrito o decidió? (si no, no se muestra)."""
        return bool(self.reason or self.lessons or (self.label and self.label != UNLABELED))

    def to_dict(self, *, include_private: bool = False) -> Dict[str, Any]:
        out = asdict(self)
        if not include_private:
            out.pop("reason_by_email", None)
        out["lessons"] = [asdict(lesson) for lesson in self.lessons]
        out["projects"] = list(self.projects)
        out["label_text"] = LABEL_TEXT.get(self.label or "")
        out["has_memory"] = self.has_memory
        return out


def clip(text: Optional[str], limit: int) -> str:
    """Recorta a `limit` caracteres en un límite de palabra, con «…»."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit // 2 else cut) + "…"


# Controles (ESC de colores de terminal…) y marcas bidi (U+202E invierte el texto).
_INVISIBLE = re.compile("[\x00-\x08\x0b-\x1f\x7f‎‏‪-‮⁦-⁩]")
# Lo que en Markdown de GitHub crea enlaces, imágenes, encabezados, código o énfasis.
_MD_SPECIAL = re.compile(r"([\\`*_\[\]()#!|~])")
_ZWSP = "​"   # rompe «@usuario» (no notifica) sin cambiar lo que se lee


def _plain(text: Optional[str], limit: int = 120) -> str:
    """Una línea, sin controles ni bidi y acotada: para el log del CI."""
    return clip(_INVISIBLE.sub("", text or ""), limit)


def _md_safe(text: Optional[str], limit: int = 120) -> str:
    """Texto escrito por personas → Markdown inerte: sin enlaces, imágenes (rastreo),
    encabezados ni referencias a issues; menciones sin notificar y HTML escapado.
    No es saneado de secretos (ya viene saneado del repositorio)."""
    text = _MD_SPECIAL.sub(r"\\\1", _plain(text, limit))
    return (text.replace("@", "@" + _ZWSP)
                .replace("<", "&lt;")
                .replace(">", "&gt;"))


def _date(iso: Optional[str]) -> str:
    return (iso or "")[:10]


def _family_heading(mem: FamilyMemory) -> str:
    parts = []
    if mem.label and mem.label != UNLABELED:
        parts.append(f"el equipo la etiquetó como **{LABEL_TEXT.get(mem.label, mem.label)}**")
    if mem.runs:
        parts.append(f"vista en {mem.runs} run{'s' if mem.runs != 1 else ''}")
    if len(mem.projects) > 1:
        parts.append("proyectos: " + ", ".join(_md_safe(p, 60) for p in mem.projects[:8]))
    head = f"**{_md_safe(mem.title)}**"
    return head + (" — " + " · ".join(parts) if parts else "")


def _author(mem: FamilyMemory) -> str:
    who = clip(mem.reason_by, 60) or "alguien del equipo"
    if not mem.reason_by_active:
        who += " (ya no está en la organización)"
    when = _date(mem.reason_at)
    return f"{who}, {when}" if when else who


def render_family_markdown(mem: FamilyMemory, *, link: Optional[str] = None) -> str:
    """Bloque Markdown de UNA familia (check run y ticket)."""
    lines = [_family_heading(mem)]
    if mem.reason:
        lines.append(f"> {_md_safe(mem.reason, MAX_REASON_CHARS)}")
        lines.append(f"> — {_md_safe(_author(mem), 160)}")
    for lesson in mem.lessons[:MAX_LESSONS]:
        summary = _md_safe(lesson.summary, MAX_LESSON_CHARS)
        text = _md_safe(lesson.title) + (f": {summary}" if summary else "")
        lines.append(f"- Lección: {text}")
    if link:
        lines.append(f"[Ver en Mnemo]({link})")
    return "\n".join(lines)


def family_link(app_url: str, family_id: str) -> Optional[str]:
    return f"{app_url.rstrip('/')}/app/defects?family={family_id}" if app_url else None


def _remembered(memories: Iterable[FamilyMemory]) -> List[FamilyMemory]:
    return [m for m in memories if m.has_memory]


def render_markdown(memories: Iterable[FamilyMemory], *, app_url: str = "",
                    limit: int = MAX_FAMILIES,
                    max_chars: int = MAX_MARKDOWN_CHARS) -> str:
    """Sección «Lo que Mnemo recuerda» para el check run. "" si no hay memoria."""
    remembered = _remembered(memories)
    if not remembered:
        return ""
    header = "### Lo que Mnemo recuerda"
    blocks: List[str] = []
    used = len(header)
    for mem in remembered[:limit]:
        block = render_family_markdown(mem, link=family_link(app_url, mem.family_id))
        if used + len(block) + 2 > max_chars:
            break
        blocks.append(block)
        used += len(block) + 2
    rest = len(remembered) - len(blocks)
    if rest > 0:
        blocks.append(f"_…y {rest} familia{'s' if rest != 1 else ''} más con memoria en Mnemo._")
    return "\n\n".join([header, *blocks])


def render_text(memories: Iterable[FamilyMemory], *, limit: int = MAX_FAMILIES) -> str:
    """Texto plano para el log del CI (GitLab, Jenkins, Actions sin App). "" si no hay."""
    remembered = _remembered(memories)
    if not remembered:
        return ""
    lines = ["Lo que Mnemo recuerda de los fallos de este run:"]
    for mem in remembered[:limit]:
        label = LABEL_TEXT.get(mem.label or "")
        lines.append(f"* {_plain(mem.title)}" + (f" [{label}]" if label else ""))
        if mem.reason:
            lines.append(f"    Por qué: {_plain(mem.reason, MAX_REASON_CHARS)}"
                         f" ({_plain(_author(mem), 160)})")
        for lesson in mem.lessons[:MAX_LESSONS]:
            lines.append(f"    Lección: {_plain(lesson.title)}")
    rest = len(remembered) - min(len(remembered), limit)
    if rest > 0:
        lines.append(f"…y {rest} más en Mnemo.")
    return "\n".join(lines)


def memory_payload(memories: Iterable[FamilyMemory], *,
                   limit: int = MAX_FAMILIES) -> Optional[Dict[str, Any]]:
    """Bloque `memory` de la respuesta del CI. None si no hay nada que contar."""
    memories = list(memories)
    remembered = _remembered(memories)
    if not remembered:
        return None
    return {"families": [m.to_dict() for m in remembered[:limit]],
            "remembered": len(remembered),
            "text": render_text(memories, limit=limit)}


def memory_summary_payload(memories: Iterable[FamilyMemory], *, app_url: str = "",
                           limit: int = MAX_FAMILIES) -> Optional[Dict[str, Any]]:
    """Versión SIN el contenido (razones, lecciones, autores) para quien solo tiene un
    token de ingesta o el webhook: un token no es un miembro, y el log del CI puede ser
    público. Recuento, títulos (salen del propio informe) y enlace a la app."""
    remembered = _remembered(memories)
    if not remembered:
        return None
    families = [{"family_id": m.family_id, "title": _plain(m.title),
                 "label_text": LABEL_TEXT.get(m.label or ""),
                 "url": family_link(app_url, m.family_id)} for m in remembered[:limit]]
    n = len(remembered)
    where = f" Detalle para miembros: {app_url.rstrip('/')}/app/defects" if app_url else ""
    text = (f"Mnemo tiene memoria del equipo sobre {n} familia{'s' if n != 1 else ''} "
            f"de los fallos de este run.{where}")
    return {"families": families, "remembered": n, "text": text, "detail": False}
