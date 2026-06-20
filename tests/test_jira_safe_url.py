import pytest

from src.jira import safe_url
from src.jira.safe_url import validate_base_url


def _fake_resolve(ip):
    def _resolver(host, port, *a, **k):
        return [(2, 1, 6, "", (ip, port or 443))]
    return _resolver


def test_accepts_public_https(monkeypatch):
    monkeypatch.setattr(safe_url.socket, "getaddrinfo", _fake_resolve("93.184.216.34"))
    assert validate_base_url("https://acme.atlassian.net/") == "https://acme.atlassian.net"


def test_rejects_http(monkeypatch):
    monkeypatch.setattr(safe_url.socket, "getaddrinfo", _fake_resolve("93.184.216.34"))
    with pytest.raises(ValueError):
        validate_base_url("http://acme.atlassian.net")


def test_rejects_loopback(monkeypatch):
    monkeypatch.setattr(safe_url.socket, "getaddrinfo", _fake_resolve("127.0.0.1"))
    with pytest.raises(ValueError):
        validate_base_url("https://localhost")


def test_rejects_private(monkeypatch):
    monkeypatch.setattr(safe_url.socket, "getaddrinfo", _fake_resolve("10.0.0.5"))
    with pytest.raises(ValueError):
        validate_base_url("https://internal.jira")


def test_rejects_metadata(monkeypatch):
    monkeypatch.setattr(safe_url.socket, "getaddrinfo", _fake_resolve("169.254.169.254"))
    with pytest.raises(ValueError):
        validate_base_url("https://evil.example")
