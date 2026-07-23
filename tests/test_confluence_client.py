"""Cliente Confluence (misma dependencia y credenciales que Jira) + parseo de URL.

El host de la URL pegada debe COINCIDIR con el base_url configurado — si no, None
(corrección, no seguridad: jamás se llama al host pegado; el fetch va SIEMPRE al
site configurado por pageId)."""
from unittest.mock import patch

import pytest

from src.confluence.client import (
    ConfluenceApiClient, ConfluenceApiError, html_to_text, parse_confluence_url)


# ── parse_confluence_url ─────────────────────────────────────────────────────

BASE = "https://acme.atlassian.net"


def test_parse_url_valida_del_site_configurado():
    ref = parse_confluence_url(
        f"{BASE}/wiki/spaces/QA/pages/12345/Titulo-de-pagina", BASE)
    assert ref is not None
    assert ref.page_id == "12345"
    assert ref.space_key == "QA"


def test_parse_url_sin_espacio_en_la_ruta():
    ref = parse_confluence_url(f"{BASE}/wiki/pages/9/T", BASE)
    assert ref is not None
    assert ref.page_id == "9"
    assert ref.space_key == ""


def test_parse_url_de_otro_site_none():
    assert parse_confluence_url(
        "https://otro.atlassian.net/wiki/spaces/QA/pages/12345/T", BASE) is None


def test_parse_url_sin_page_id_none():
    assert parse_confluence_url(f"{BASE}/wiki/spaces/QA/overview", BASE) is None


def test_parse_url_page_id_no_numerico_none():
    assert parse_confluence_url(f"{BASE}/wiki/spaces/QA/pages/abc/T", BASE) is None


def test_parse_base_url_con_barra_final():
    ref = parse_confluence_url(f"{BASE}/wiki/spaces/QA/pages/7/T", BASE + "/")
    assert ref is not None and ref.page_id == "7"


# ── html_to_text ─────────────────────────────────────────────────────────────

def test_html_to_text_aplana_y_colapsa():
    html = "<h1>Reglas</h1><p>Hola <b>mundo</b>.</p>\n<ul><li>a</li><li>b</li></ul>"
    assert html_to_text(html) == "Reglas Hola mundo. a b"


def test_html_to_text_ignora_script_y_style():
    html = "<p>visible</p><script>alert(1)</script><style>.x{}</style>"
    assert html_to_text(html) == "visible"


# ── ConfluenceApiClient ──────────────────────────────────────────────────────

def test_fetch_page_devuelve_titulo_texto_y_space():
    with patch("src.confluence.client.Confluence") as mock_conf:
        api = mock_conf.return_value
        api.get_page_by_id.return_value = {
            "id": "12345", "title": "Reglas de pagos",
            "space": {"key": "QA"},
            "body": {"storage": {"value": "<p>Hola <b>mundo</b></p>"}},
        }
        client = ConfluenceApiClient(BASE, "e@x.com", "tok")
        page = client.fetch_page("12345")
    # el cliente apunta al site configurado + /wiki, con timeout explícito
    kwargs = mock_conf.call_args.kwargs
    assert kwargs["url"] == f"{BASE}/wiki"
    assert kwargs["timeout"] == 10
    assert kwargs["cloud"] is True
    assert page.title == "Reglas de pagos"
    assert page.text == "Hola mundo"
    assert page.space_key == "QA"
    api.get_page_by_id.assert_called_once_with("12345", expand="body.storage,space")


def test_fetch_page_error_de_la_libreria_envuelto():
    with patch("src.confluence.client.Confluence") as mock_conf:
        mock_conf.return_value.get_page_by_id.side_effect = Exception("404 Not Found")
        client = ConfluenceApiClient(BASE, "e@x.com", "tok")
        with pytest.raises(ConfluenceApiError):
            client.fetch_page("999")
