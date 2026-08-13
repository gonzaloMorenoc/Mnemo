"""Los datos del escenario María→Pablo: forma, kinds y ninguna filtración."""
import re

from src.demo.continuity_data import CONTINUITY_ITEMS

_OFICIO = {"runbook", "dato_prueba", "contacto", "decision"}

# Números de tarjeta de PRUEBA públicos del sandbox (los únicos permitidos).
_TARJETAS_PERMITIDAS = {"4111111111111111", "4000000000000002"}


def _texto(item):
    return " ".join(str(item.get(k) or "") for k in ("title", "challenge", "approach", "outcome"))


def test_son_nueve_items_del_proyecto_de_maria():
    assert len(CONTINUITY_ITEMS) == 9
    assert all(i["project"] == "checkout-suite" for i in CONTINUITY_ITEMS)


def test_cubren_los_cuatro_kinds_del_oficio():
    kinds = [i["kind"] for i in CONTINUITY_ITEMS]
    for kind in _OFICIO:
        assert kinds.count(kind) == 2, f"{kind}: se esperaban 2"
    assert kinds.count("leccion") == 1


def test_la_leccion_respalda_el_dominio_pagos():
    # Es la que sube reglas_respaldadas de 2/5 a 4/5: los dos items sin respaldo
    # de 'pagos'. 'catalogo' queda sin respaldar A PROPÓSITO (el 95-y-no-100).
    leccion = next(i for i in CONTINUITY_ITEMS if i["kind"] == "leccion")
    assert leccion["domain"] == "pagos"


def test_titulos_unicos_porque_son_la_clave_de_idempotencia():
    titulos = [i["title"] for i in CONTINUITY_ITEMS]
    assert len(titulos) == len(set(titulos))


def test_ninguna_tarjeta_fuera_de_las_de_prueba():
    for item in CONTINUITY_ITEMS:
        for numero in re.findall(r"\d[\d\s-]{11,}\d", _texto(item)):
            limpio = re.sub(r"[\s-]", "", numero)
            assert limpio in _TARJETAS_PERMITIDAS, f"número sospechoso: {numero!r}"


def test_los_contactos_son_roles_no_personas():
    # Decisión de #106: equipos y canales, no personas. Un email en un contacto
    # delataría que se coló una persona (los canales #x no llevan @).
    for item in CONTINUITY_ITEMS:
        if item["kind"] == "contacto":
            assert "@" not in _texto(item), f"email en un contacto: {item['title']}"
