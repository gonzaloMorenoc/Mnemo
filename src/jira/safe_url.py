import ipaddress
import socket
from urllib.parse import urlparse


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
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError("La URL de Jira apunta a una dirección no permitida")
    return url.strip().rstrip("/")


def no_redirect_session() -> "requests.Session":
    """Sesión HTTP que NO sigue redirecciones. validate_base_url filtra el host, pero
    un 302 desde un host externo hacia una IP interna saltaba ese filtro. Las APIs de
    Atlassian Cloud no redirigen en uso normal: una redirección se corta."""
    import requests

    session = requests.Session()
    session.max_redirects = 0
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
