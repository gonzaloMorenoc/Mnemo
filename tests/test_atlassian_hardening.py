"""Endurecimiento de los clientes Jira/Confluence (SSRF y exfiltración).

validate_base_url comprueba que el host no resuelve a una IP interna, pero la
librería seguía redirecciones: un 302 desde un host externo hacia una IP interna
saltaba el filtro. Y el texto crudo de la excepción (que puede llevar el cuerpo de
la respuesta) llegaba al usuario en el resultado del import: un canal ciego para
leer lo que devuelve el destino."""
from unittest.mock import MagicMock

import pytest
import requests

from src.confluence.client import ConfluenceApiClient, ConfluenceApiError
from src.jira.client import JiraApiClient, JiraApiError
from src.jira.safe_url import no_redirect_session, safe_error


def test_clients_use_a_session_that_never_follows_redirects():
    for client in (JiraApiClient("https://acme.atlassian.net", "e", "t")._jira,
                   ConfluenceApiClient("https://acme.atlassian.net", "e", "t")._confluence):
        assert client.session.max_redirects == 0


def test_no_redirect_session_refuses_a_302():
    assert no_redirect_session().max_redirects == 0


def _http_error(status, body):
    resp = requests.Response()
    resp.status_code = status
    resp._content = body.encode()
    return requests.HTTPError(f"{status} Client Error: {body}", response=resp)


def test_safe_error_keeps_the_status_and_drops_the_body():
    msg = safe_error(_http_error(404, "secreto interno: db=10.0.0.5 user=root"))
    assert "404" in msg and "secreto" not in msg and "10.0.0.5" not in msg


@pytest.mark.parametrize("exc,esperado", [
    (requests.TooManyRedirects("Exceeded 0 redirects."), "redirección"),
    (requests.ConnectionError("Max retries … host interno"), "conectar"),
    (requests.Timeout("read timeout"), "tiempo"),
    (RuntimeError("cualquier otra cosa con datos"), "no se pudo"),
])
def test_safe_error_never_echoes_the_exception_text(exc, esperado):
    msg = safe_error(exc)
    assert esperado in msg.lower() and "datos" not in msg and "interno" not in msg


def test_client_errors_carry_the_safe_message():
    c = JiraApiClient("https://acme.atlassian.net", "e", "t")
    c._jira = MagicMock()
    c._jira.issue.side_effect = _http_error(500, "stacktrace con rutas internas")
    with pytest.raises(JiraApiError) as e:
        c.fetch_issue("ABC-1")
    assert "stacktrace" not in str(e.value) and "500" in str(e.value)

    cf = ConfluenceApiClient("https://acme.atlassian.net", "e", "t")
    cf._confluence = MagicMock()
    cf._confluence.get_page_by_id.side_effect = _http_error(404, "cuerpo de la página interna")
    with pytest.raises(ConfluenceApiError) as e:
        cf.fetch_page("123")
    assert "cuerpo" not in str(e.value) and "404" in str(e.value)
