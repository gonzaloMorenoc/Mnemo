"""Un FailureRecord crudo → IngestItem listo para la ingesta (huella, saneado, embedding).

Antes vivía copiado en cada servicio de ingesta y saneaba ANTES de calcular la
huella (auditoría 23-nov, #3). El orden importa:
  1. la huella sale del registro CRUDO con su normalización propia (fingerprint.py),
     así no depende de lo que el saneador de privacidad decida redactar;
  2. lo que se guarda y lo que se embebe es el texto SANEADO;
  3. si el mensaje no informa (vacío, «Failed»), no se embebe una cadena vacía
     —todos esos fallos compartirían vector y se fusionarían por coseno—: se
     embebe la primera línea de la traza más la identidad del test, y el fallo
     solo se une a una familia por huella exacta, nunca por similitud;
  4. lo mismo si el saneador redactó algo del mensaje: dos fallos que solo se
     distinguían por la URL o la ruta tienen el MISMO texto saneado (coseno 1,0)
     y se fusionarían por similitud aunque sus huellas difieran. Ante la duda, no
     fusionar (mismo criterio que MATCH_THRESHOLD en match.py): el mismo defecto
     sigue cayendo en su familia por huella exacta.
"""
from dataclasses import replace

from src.defects.embedder import Embedder
from src.defects.fingerprint import failure_summary, fingerprint, is_informative
from src.defects.repository import IngestItem
from src.ingest.models import FailureRecord
from src.sanitizer import sanitize_text


def sanitized_record(rec: FailureRecord) -> FailureRecord:
    """Copia del registro con mensaje y traza saneados (lo que se persiste)."""
    return replace(rec, message=sanitize_text(rec.message),
                   trace=sanitize_text(rec.trace) if rec.trace else None)


def embedding_source(clean: FailureRecord) -> str:
    """Texto a embeber a partir del registro YA saneado. Nunca vacío."""
    if is_informative(clean.message):
        return f"{clean.error_type or ''} {clean.message}".strip()
    parts = (clean.error_type or "", failure_summary(clean), clean.test_name or "")
    return " ".join(p.strip() for p in parts if p and p.strip()) or "unknown"


def similarity_allowed(rec: FailureRecord, clean: FailureRecord) -> bool:
    """¿Puede este fallo unirse a una familia por coseno? Solo si su mensaje
    informa y el saneado no le quitó nada (ver puntos 3 y 4 del módulo)."""
    return is_informative(rec.message) and clean.message == rec.message


def build_ingest_item(rec: FailureRecord, embedder: Embedder) -> IngestItem:
    """Huella del crudo + registro saneado + embedding del saneado."""
    clean = sanitized_record(rec)
    return IngestItem(
        rec=clean,
        fingerprint=fingerprint(rec),
        embedding=embedder.embed(embedding_source(clean)),
        allow_similarity=similarity_allowed(rec, clean),
    )
