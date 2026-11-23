"""Patrones del sanitizer (auditoría 23-nov, #17 / H5): secretos tipo gitleaks,
datos personales de España y saneado completo de textos largos.

Cada patrón tiene casos positivos (se redacta) y negativos (no se toca): una traza
de stack típica no debe perder información por falsos positivos.
"""
import time

import pytest

from src.sanitizer import sanitize_text

# Valores sintéticos, no secretos reales: formatos válidos para los patrones.
_JWT = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c")
_GHP = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
_PEM = ("-----BEGIN PRIVATE KEY-----\n"
        "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7\n"
        "aGVsbG8gd29ybGQgdGhpcyBpcyBub3QgYSByZWFsIGtleQ==\n"
        "-----END PRIVATE KEY-----")


@pytest.mark.parametrize("raw, secret", [
    (f"Authorization: Bearer {_JWT}", _JWT),
    (f"token suelto {_JWT} en el log", _JWT),
    ("Authorization: Basic dXNlcjpwYXNzd29yZA==", "dXNlcjpwYXNzd29yZA=="),
    ("curl -H 'Authorization: Basic dXNlcjpwYXNz'", "dXNlcjpwYXNz"),
    ("Bearer abcdefghijklmnop1234", "abcdefghijklmnop1234"),
    ("aws key AKIAIOSFODNN7EXAMPLE used", "AKIAIOSFODNN7EXAMPLE"),
    ("aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
     "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"),
    (f"GITHUB_TOKEN {_GHP}", _GHP),
    ("gho_" + "x" * 36, "gho_" + "x" * 36),
    ("ghs_" + "Z9" * 18, "ghs_" + "Z9" * 18),
    ("github_pat_11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz",
     "github_pat_11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz"),
    ("postgresql://admin:s3cr3tPass@db.example.com:5432/app", "s3cr3tPass"),
])
def test_redacta_secretos(raw, secret):
    out = sanitize_text(raw)
    assert secret not in out
    assert "[REDACTED" in out


def test_redacta_bloque_pem_completo():
    out = sanitize_text(f"config:\n{_PEM}\nfin")
    assert "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7" not in out
    assert "BEGIN PRIVATE KEY" not in out
    assert "[REDACTED_PRIVATE_KEY]" in out
    assert out.endswith("fin")


def test_redacta_pem_sin_cierre():
    truncated = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAu1SU1LfVLPHCozMxH2Mo4lgOEePzNm0tRgeLezV6ffAt0gun\n"
    out = sanitize_text(truncated + "siguiente linea normal")
    assert "MIIEowIBAAKCAQEAu1SU1LfVLPHCozMxH2Mo4lgOEePzNm0tRgeLezV6ffAt0gun" not in out
    assert "siguiente linea normal" in out


@pytest.mark.parametrize("raw, dato", [
    ("cliente con DNI 12345678Z en el formulario", "12345678Z"),
    ("dni: 00000000-T", "00000000-T"),
    ("NIE X1234567L registrado", "X1234567L"),
    ("IBAN ES9121000418450200051332 del cliente", "ES9121000418450200051332"),
    ("iban: ES91 2100 0418 4502 0005 1332", "ES91 2100 0418 4502 0005 1332"),
    ("llamar al +34 612 345 678", "612 345 678"),
    ("tel 0034612345678", "0034612345678"),
    ("móvil: 612-345-678", "612-345-678"),
    ("teléfono 912 34 56 78", "912 34 56 78"),
    ("Teléfono: 612345678", "612345678"),
    ("phone +1 415 555 2671", "415 555 2671"),
])
def test_redacta_datos_personales_es(raw, dato):
    out = sanitize_text(raw)
    assert dato not in out
    assert "[REDACTED" in out


@pytest.mark.parametrize("raw", [
    # DNI con letra de control incorrecta: no es un DNI
    "pedido 12345678A en cola",
    # IBAN con dígitos de control incorrectos
    "ref ES0021000418450200051332",
    # números de 9 cifras sin contexto de teléfono (ids, duraciones)
    "order id 612345678 not found",
    "took 912345678 ns",
    # palabras corrientes tras Basic/Bearer
    "Basic authentication failed for user",
    "Bearer token missing",
    # eyJ sin forma de JWT
    "valor eyJhbGci truncado",
])
def test_sin_falsos_positivos(raw):
    assert sanitize_text(raw) == raw


def test_traza_de_stack_tipica_no_se_altera():
    trace = (
        "java.lang.AssertionError: expected:<200> but was:<500>\n"
        "\tat org.junit.Assert.fail(Assert.java:89)\n"
        "\tat com.acme.checkout.CheckoutIT.payWithCard(CheckoutIT.java:142)\n"
        "\tat java.base/jdk.internal.reflect.NativeMethodAccessorImpl.invoke0(Native Method)\n"
        "TimeoutError: page.click: Timeout 30000ms exceeded.\n"
        "  at Context.<anonymous> (tests/e2e/login.spec.ts:57:15)\n"
        "  id=123e4567-e89b-12d3-a456-426614174000 at 2026-11-23T10:00:00+01:00\n"
        "  addr 0x7ffeefbff5c8 retries=3 elapsed=1234567ms\n"
    )
    out = sanitize_text(trace)
    for keep in ("expected:<200> but was:<500>", "CheckoutIT.java:142", "Timeout 30000ms",
                 "123e4567-e89b-12d3-a456-426614174000", "0x7ffeefbff5c8",
                 "elapsed=1234567ms", "2026-11-23T10:00:00+01:00"):
        assert keep in out


def test_sanea_mas_alla_de_20000_caracteres():
    filler = "linea de log normal sin datos\n" * 2000   # ~60.000 caracteres
    raw = filler + f"Authorization: Bearer {_JWT}\n" + "IBAN ES9121000418450200051332\n"
    out = sanitize_text(raw)
    assert _JWT not in out
    assert "ES9121000418450200051332" not in out
    assert out.startswith("linea de log normal")


def test_secreto_justo_en_el_corte_de_trozo():
    # el corte se hace por líneas: un token no se parte por la mitad
    raw = ("x" * 99 + "\n") * 199 + "y" * 60 + f" {_GHP}\n" + "z\n" * 10
    out = sanitize_text(raw)
    assert _GHP not in out


def test_coste_lineal_en_textos_enormes():
    big = ("a." * 40 + " user@ " + "/" * 30 + "\n") * 25_000   # ~2,6 MB
    start = time.monotonic()
    sanitize_text(big + f"Bearer {_JWT}")
    assert time.monotonic() - start < 10.0


def test_texto_vacio():
    assert sanitize_text("") == ""
