"""Regresión de calidad del embebedor en ESPAÑOL (auditoría 2026-08-12, H2).

Todo el contenido de la memoria está en español; con all-MiniLM-L6-v2 (inglés)
el margen entre un par relacionado y uno sin relación era 0,05 — la búsqueda
semántica no discriminaba. Este test fija el contrato: el modelo configurado
tiene que separar señal de ruido en español con un margen holgado.

Marcado integration: descarga el modelo (~470 MB) — el CI lo excluye.
"""
import math

import pytest

from src.defects.embedder import LocalEmbedder

pytestmark = pytest.mark.integration


def _sim(e: LocalEmbedder, a: str, b: str) -> float:
    va, vb = e.embed(a), e.embed(b)
    dot = sum(x * y for x, y in zip(va, vb))
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(y * y for y in vb))
    return dot / (na * nb)


def test_dimensiones_compatibles_con_el_esquema():
    # Todas las columnas son vector(384): un modelo de otra dimensión rompería la BD.
    assert len(LocalEmbedder().embed("hola")) == 384


def test_discrimina_senal_de_ruido_en_espanol():
    e = LocalEmbedder()
    relacionado = _sim(e, "el pago con tarjeta falla en el checkout",
                       "error al procesar la transacción de la tarjeta de crédito")
    ruido = _sim(e, "el pago con tarjeta falla en el checkout",
                 "la ruta de aprendizaje del nuevo QA dura tres días")
    # Con MiniLM-L6 (inglés) este margen era 0,05. El multilingüe da ~0,66.
    # Umbral en 0,30: holgado contra la variación entre versiones del modelo,
    # imposible de pasar para un modelo que no entienda español.
    assert relacionado - ruido > 0.30, (
        f"margen señal/ruido insuficiente en español: {relacionado - ruido:.3f}")


def test_cruzado_espanol_ingles():
    # Los imports de Jira/Confluence llegan a menudo en inglés; una consulta en
    # español tiene que encontrarlos.
    e = LocalEmbedder()
    cruzado = _sim(e, "el pago con tarjeta falla en el checkout",
                   "error processing the credit card transaction")
    assert cruzado > 0.45, f"similitud cruzada ES-EN insuficiente: {cruzado:.3f}"
