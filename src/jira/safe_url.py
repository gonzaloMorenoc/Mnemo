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
