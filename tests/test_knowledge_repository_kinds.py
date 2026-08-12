"""Los kinds operativos (auditoría 12-ago, H3): sitio para el oficio del proyecto.

Los 7 kinds originales describen el PRODUCTO y sus fallos. Lo que de verdad se va
cuando se va el QA senior —cómo se levanta el entorno, con qué datos se prueba, qué
equipo lleva cada cosa, qué se acordó no hacer— no tenía dónde vivir: el CHECK de la
migración 018 lo rechazaba y acababa disfrazado de "glosario", es decir, inencontrable.
"""
from unittest.mock import MagicMock

import pytest

from src.knowledge.repository import KINDS, insert_qa_knowledge

_OPERATIVOS = ("runbook", "dato_prueba", "contacto", "decision")


def _insert(cur, kind):
    return insert_qa_knowledge(
        cur, org_id="00000000-0000-0000-0000-000000000001", kind=kind,
        title="t", challenge=None, approach=None, outcome=None, domain=None,
        tags=None, project=None, source="manual", confidence="confirmado",
        defect_family_id=None, run_id=None, created_by="u", embedding=None)


@pytest.mark.parametrize("kind", _OPERATIVOS)
def test_kinds_operativos_estan_en_el_contrato(kind):
    # KINDS es el export que consume el refine para validar lo que propone el LLM.
    assert kind in KINDS


@pytest.mark.parametrize("kind", _OPERATIVOS)
def test_insert_acepta_los_kinds_operativos(kind):
    cur = MagicMock()
    cur.fetchone.return_value = {"id": "x", "kind": kind}
    _insert(cur, kind)
    assert cur.execute.called


def test_insert_sigue_rechazando_un_kind_inventado():
    with pytest.raises(ValueError, match="kind inválido"):
        _insert(MagicMock(), "inventado")


def test_los_kinds_de_producto_siguen_intactos():
    # La migración es aditiva: nada de lo que ya funcionaba deja de funcionar.
    for kind in ("regla_negocio", "flujo", "riesgo", "glosario", "leccion", "reto", "patron"):
        assert kind in KINDS
