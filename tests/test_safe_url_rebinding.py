"""DNS rebinding en Jira/Confluence (auditoría 23-nov, H9.1).

validate_base_url resuelve el host y comprueba la IP, pero la petición vuelve a
resolver: un DNS malicioso puede contestar una IP pública a la validación y una
interna a la conexión. Ahora se revalida la IP del socket YA conectado, así que da
igual lo que conteste el DNS. Resolvers y sockets simulados: sin red."""
import ipaddress

import pytest
import requests
import urllib3.util.connection as urllib3_connection
from urllib3.exceptions import NewConnectionError

from src.jira import safe_url
from src.jira.safe_url import (
    PeerCheckedHTTPSConnection,
    is_forbidden_ip,
    no_redirect_session,
    validate_base_url,
)


class _FakeSock:
    def __init__(self, peer):
        self.peer = peer
        self.closed = False
        self.sent = []

    def getpeername(self):
        return (self.peer, 443)

    def close(self):
        self.closed = True

    def sendall(self, data):
        self.sent.append(data)

    def settimeout(self, *_):
        pass

    def setsockopt(self, *_):
        pass


def _connect_to(peer, socks):
    def _create_connection(address, *a, **k):
        sock = _FakeSock(peer)
        socks.append(sock)
        return sock
    return _create_connection


@pytest.mark.parametrize("ip", [
    "10.0.0.5", "127.0.0.1", "169.254.169.254", "100.64.0.1",   # CGNAT incluido
    "0.0.0.0", "::1", "fd00::1", "::ffff:10.0.0.1", "224.0.0.1",
])
def test_ips_no_permitidas(ip):
    assert is_forbidden_ip(ipaddress.ip_address(ip)) is True


@pytest.mark.parametrize("ip", ["93.184.216.34", "2606:4700::6810:84e5"])
def test_ips_publicas(ip):
    assert is_forbidden_ip(ipaddress.ip_address(ip)) is False


def test_conexion_a_ip_interna_se_corta(monkeypatch):
    socks = []
    monkeypatch.setattr(urllib3_connection, "create_connection", _connect_to("10.0.0.5", socks))
    conn = PeerCheckedHTTPSConnection("acme.atlassian.net", 443)
    with pytest.raises(NewConnectionError):
        conn._new_conn()
    assert socks[0].closed


def test_conexion_a_ip_publica_sigue(monkeypatch):
    socks = []
    monkeypatch.setattr(urllib3_connection, "create_connection", _connect_to("93.184.216.34", socks))
    conn = PeerCheckedHTTPSConnection("acme.atlassian.net", 443)
    assert conn._new_conn() is socks[0] and not socks[0].closed


def test_rebinding_validacion_publica_conexion_interna(monkeypatch):
    """El DNS contesta pública al validar e interna al conectar: la petición no sale."""
    monkeypatch.setattr(safe_url.socket, "getaddrinfo",
                        lambda host, port, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    base = validate_base_url("https://rebind.example")
    socks = []
    monkeypatch.setattr(urllib3_connection, "create_connection", _connect_to("169.254.169.254", socks))
    with pytest.raises(requests.ConnectionError):
        no_redirect_session().get(f"{base}/rest/api/2/myself", timeout=1)
    assert socks and socks[0].closed and socks[0].sent == []


def test_la_sesion_no_usa_proxies_del_entorno():
    # Con un proxy, la IP conectada sería la del proxy y no se podría revalidar.
    assert no_redirect_session().trust_env is False


def test_validate_base_url_rechaza_cgnat(monkeypatch):
    monkeypatch.setattr(safe_url.socket, "getaddrinfo",
                        lambda host, port, *a, **k: [(2, 1, 6, "", ("100.64.1.2", 443))])
    with pytest.raises(ValueError):
        validate_base_url("https://cgnat.example")
