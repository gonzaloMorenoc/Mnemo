"""Ingestion of HU (User Story) files for the Test Plan Agent.

Supports: PDF (.pdf via pypdf), Word (.docx via python-docx), plain text (.txt).
Size cap: 5 MB.  Sensitive content is sanitized via src.sanitizer.sanitize_text.
"""

from __future__ import annotations

import io
from pathlib import PurePosixPath

import pypdf
import docx as python_docx

from src.sanitizer import sanitize_text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Hard cap on accepted file size.  Files larger than this are rejected before
#: any parsing to avoid memory exhaustion and DoS via crafted documents.
MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024  # 5 MB

_SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx", ".txt"})


# ---------------------------------------------------------------------------
# Low-level extractors
# ---------------------------------------------------------------------------


def text_from_pdf(data: bytes) -> str:
    """Extract all text from a PDF given as raw bytes.

    Parameters
    ----------
    data:
        Raw bytes of a PDF document.

    Returns
    -------
    str
        Concatenated text from all pages, separated by newlines.

    Raises
    ------
    ValueError
        If *data* cannot be parsed as a valid PDF.
    """
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"PDF no válido: {exc}") from exc

    pages: list[str] = []
    for page in reader.pages:
        extracted = page.extract_text() or ""
        pages.append(extracted)

    return "\n".join(pages)


def text_from_docx(data: bytes) -> str:
    """Extract all paragraph text from a DOCX document given as raw bytes.

    Parameters
    ----------
    data:
        Raw bytes of a DOCX (Office Open XML) document.

    Returns
    -------
    str
        Paragraphs joined with newlines.

    Raises
    ------
    ValueError
        If *data* cannot be parsed as a valid DOCX file.
    """
    try:
        doc = python_docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"DOCX no válido: {exc}") from exc

    paragraphs = [p.text for p in doc.paragraphs]
    return "\n".join(paragraphs)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def resolve_hu_from_upload(filename: str, data: bytes) -> str:
    """Dispatch ingestion by file extension, validate size, and sanitize.

    Parameters
    ----------
    filename:
        Original filename (used only to determine extension).
    data:
        Raw file bytes.

    Returns
    -------
    str
        Extracted and sanitized plain text of the user story.

    Raises
    ------
    ValueError
        If the file extension is not supported (`.pdf`/`.docx`/`.txt`) or the
        file exceeds :data:`MAX_UPLOAD_BYTES`.
    """
    # --- size guard ---
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"El archivo supera el tamaño máximo permitido de "
            f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB. "
            f"Tamaño recibido: {len(data)} bytes."
        )

    # --- extension guard ---
    ext = PurePosixPath(filename.lower()).suffix
    if ext not in _SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"extensión no soportada: '{ext}'. "
            f"Formatos válidos: {sorted(_SUPPORTED_EXTENSIONS)}."
        )

    # --- dispatch ---
    if ext == ".pdf":
        raw_text = text_from_pdf(data)
    elif ext == ".docx":
        raw_text = text_from_docx(data)
    else:  # .txt
        try:
            raw_text = data.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = data.decode("latin-1")

    # --- sanitize ---
    return sanitize_text(raw_text)
