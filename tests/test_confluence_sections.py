"""Seccionado del HTML de Confluence (auditoría 12-ago, H4b).

Antes, cada página se truncaba a 2.000 caracteres: la estrategia de pruebas del
proyecto se convertía en un muñón con un enlace. Ahora entra por secciones.

El corte tiene que hacerse aquí, sobre el HTML: html_to_text colapsa todo el
whitespace, así que en el texto plano los <h1>…<h6> ya son indistinguibles del
cuerpo y no hay nada que cortar.
"""
from src.confluence.client import html_to_sections

_PAGINA = """
<h1>Entorno de pruebas</h1>
<p>Levantar con docker compose up.</p>
<h2>Datos de prueba</h2>
<p>Usuario demo, tarjeta 4111.</p>
<h2>Datos de prueba</h2>
<p>Segundo bloque con el mismo título.</p>
"""


def test_corta_por_encabezados():
    secciones = html_to_sections(_PAGINA)
    assert [h for h, _ in secciones] == [
        "Entorno de pruebas", "Datos de prueba", "Datos de prueba"]


def test_el_cuerpo_acompana_a_su_encabezado():
    secciones = html_to_sections(_PAGINA)
    assert "docker compose up" in secciones[0][1]
    assert "tarjeta 4111" in secciones[1][1]
    # El cuerpo de una sección no se cuela en la siguiente.
    assert "docker compose" not in secciones[1][1]


def test_texto_antes_del_primer_encabezado_es_introduccion():
    secciones = html_to_sections("<p>Contexto suelto.</p><h2>Luego</h2><p>Cuerpo.</p>")
    assert secciones[0][0] == "Introducción"
    assert "Contexto suelto." in secciones[0][1]


def test_pagina_sin_encabezados_da_una_sola_seccion():
    secciones = html_to_sections("<p>Todo seguido, sin titulares.</p>")
    assert len(secciones) == 1
    assert secciones[0][0] == ""
    assert "Todo seguido" in secciones[0][1]


def test_html_vacio_no_da_secciones():
    assert html_to_sections("") == []


def test_descarta_secciones_sin_cuerpo():
    # Un encabezado suelto al final de la página no aporta conocimiento.
    secciones = html_to_sections("<h2>Con cuerpo</h2><p>Algo.</p><h2>Vacía</h2>")
    assert [h for h, _ in secciones] == ["Con cuerpo"]


def test_encabezados_de_cualquier_nivel():
    secciones = html_to_sections(
        "<h3>Tres</h3><p>a</p><h6>Seis</h6><p>b</p>")
    assert [h for h, _ in secciones] == ["Tres", "Seis"]


def test_ignora_script_y_style_como_el_extractor_de_texto():
    secciones = html_to_sections(
        "<h2>T</h2><p>visible</p><script>secreto()</script><style>.x{}</style>")
    assert "secreto" not in secciones[0][1]
    assert "visible" in secciones[0][1]


def test_el_marcado_inline_no_parte_las_palabras():
    secciones = html_to_sections("<h2>T</h2><p>Hola <b>mundo</b>.</p>")
    assert "Hola mundo." in secciones[0][1]
