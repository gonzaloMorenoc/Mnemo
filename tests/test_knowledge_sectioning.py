"""Drafts por sección: identidad estable y topes visibles (auditoría 12-ago, H4b)."""
from src.knowledge.sectioning import section_drafts, slugify


def test_slug_normaliza_acentos_y_espacios():
    assert slugify("Datos de prueba (PSP)") == "datos-de-prueba-psp"


def test_slug_de_encabezado_vacio_es_estable():
    assert slugify("") == "seccion"


def test_un_draft_por_seccion_con_titulo_compuesto():
    drafts, descartadas = section_drafts(
        "Manual de QA", [("Entorno", "docker compose up"), ("Datos", "usuario demo")])
    assert descartadas == 0
    assert [d["title"] for d in drafts] == ["Manual de QA — Entorno", "Manual de QA — Datos"]
    assert [d["slug"] for d in drafts] == ["entorno", "datos"]


def test_encabezados_repetidos_no_colisionan():
    # Sin sufijo, la segunda sección sobrescribiría a la primera en el upsert.
    drafts, _ = section_drafts("P", [("Datos", "uno"), ("Datos", "dos")])
    assert [d["slug"] for d in drafts] == ["datos", "datos-2"]


def test_seccion_larga_se_trunca_con_marca():
    drafts, _ = section_drafts("P", [("Larga", "x" * 5000)], max_chars=4000)
    assert drafts[0]["body"].endswith("… [contenido truncado — ver original]")
    assert drafts[0]["body"].startswith("x" * 100)


def test_por_encima_del_tope_se_descartan_y_se_cuentan():
    secciones = [(f"S{i}", "cuerpo") for i in range(15)]
    drafts, descartadas = section_drafts("P", secciones, max_sections=12)
    assert len(drafts) == 12
    assert descartadas == 3


def test_pagina_sin_encabezados_usa_el_titulo_de_la_pagina():
    drafts, _ = section_drafts("Manual de QA", [("", "todo seguido")])
    assert drafts[0]["title"] == "Manual de QA"
    assert drafts[0]["slug"] == "seccion"


def test_secciones_vacias_no_generan_draft():
    drafts, descartadas = section_drafts("P", [("A", "algo"), ("B", "   ")])
    assert len(drafts) == 1
    assert descartadas == 0


def test_sin_secciones_no_hay_drafts():
    assert section_drafts("P", []) == ([], 0)
