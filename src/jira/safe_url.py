"""Validación anti-SSRF de las URLs de Jira/Confluence y sesión HTTP endurecida.

Dos capas:
1. `validate_base_url` al guardar la config y en el momento de uso: https y un host
   que resuelva solo a IPs públicas.
2. La sesión de `no_redirect_session` revalida la IP del socket YA CONECTADO
   (auditoría 23-nov, H9.1): la petición vuelve a resolver el DNS, y un DNS
   malicioso (rebinding) podía contestar una IP pública a la validación y una
   interna a la conexión. Revalidar el socket cierra ese hueco sin tocar SNI ni la
   verificación del certificado, que siguen usando el nombre del host.
"""
import ipaddress
import socket
from typing import Union
from urllib.parse import urlparse

from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import NewConnectionError

IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


def is_forbidden_ip(ip: IPAddress) -> bool:
    """True si la IP no es pública: privada, loopback, link-local (metadatos cloud),
    CGNAT 100.64/10, reservada, multicast, sin especificar… `is_global` cubre todo eso
    salvo multicast; las IPv6 con una IPv4 mapeada se juzgan por la IPv4."""
    mapped = getattr(ip, "ipv4_mapped", None)
    target = mapped if mapped is not None else ip
    return (not target.is_global) or target.is_multicast


def validate_base_url(url: str) -> str:
    """Valida la URL base de Jira contra SSRF. Devuelve la URL normalizada o ValueError."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise ValueError("La URL de Jira debe usar https")
    host = parsed.hostname
    if not host:
        raise ValueError("URL de Jira sin host")
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"No se pudo resolver el host de Jira: {exc}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if is_forbidden_ip(ip):
            raise ValueError("La URL de Jira apunta a una dirección no permitida")
    return url.strip().rstrip("/")


class _PeerCheckMixin:
    """Tras conectar, comprueba la IP real del socket; si no es pública, lo cierra."""

    def _new_conn(self):
        sock = super()._new_conn()
        try:
            peer = sock.getpeername()[0]
            ip = ipaddress.ip_address(str(peer).split("%", 1)[0])
        except (OSError, ValueError) as exc:
            sock.close()
            raise NewConnectionError(self, "no se pudo comprobar la IP conectada") from exc
        if is_forbidden_ip(ip):
            sock.close()
            raise NewConnectionError(self, "la IP conectada no es pública (posible DNS rebinding)")
        return sock


class PeerCheckedHTTPSConnection(_PeerCheckMixin, HTTPSConnection):
    pass


class PeerCheckedHTTPConnection(_PeerCheckMixin, HTTPConnection):
    pass


class _PeerCheckedHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = PeerCheckedHTTPSConnection


class _PeerCheckedHTTPPool(HTTPConnectionPool):
    ConnectionCls = PeerCheckedHTTPConnection


class _PeerCheckedAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {
            "http": _PeerCheckedHTTPPool, "https": _PeerCheckedHTTPSPool}


def no_redirect_session() -> "requests.Session":
    """Sesión HTTP endurecida para los destinos que configura el cliente (Jira,
    Confluence):

    - NO sigue redirecciones: validate_base_url filtra el host, pero un 302 desde un
      host externo hacia una IP interna saltaba ese filtro. Las APIs de Atlassian
      Cloud no redirigen en uso normal.
    - Revalida la IP del socket conectado (anti DNS rebinding).
    - Ignora los proxies del entorno: con un proxy, la IP conectada sería la suya y la
      revalidación no serviría.
    """
    import requests

    session = requests.Session()
    session.max_redirects = 0
    session.trust_env = False
    adapter = _PeerCheckedAdapter()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def safe_error(exc: BaseException) -> str:
    """Mensaje de error apto para el usuario: el tipo de fallo y el código HTTP, nunca
    el texto de la excepción (puede llevar el cuerpo de la respuesta del destino y
    convertir el import en un canal para leerlo)."""
    import requests

    if isinstance(exc, requests.TooManyRedirects):
        return "el servidor respondió con una redirección, que no se sigue"
    if isinstance(exc, requests.Timeout):
        return "se agotó el tiempo de espera"
    if isinstance(exc, requests.ConnectionError):
        return "no se pudo conectar con el servidor"
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status:
        return f"el servidor respondió con un error HTTP {status}"
    return "no se pudo completar la petición"
