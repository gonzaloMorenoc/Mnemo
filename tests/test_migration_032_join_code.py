"""Migración 032: código de unión con caducidad y entrada como viewer (estático, sin BD)."""
import re
from pathlib import Path

from src.orgs.repository import JOIN_CODE_TTL_DAYS

_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"
_SQL = (_DIR / "032_join_code_viewer_expiry.sql").read_text()


def _function_body(sql: str) -> str:
    m = re.search(r"create or replace function public\.join_organization_by_code.*?\$\$(.*?)\$\$",
                  sql, re.S)
    assert m, "032 debe redefinir join_organization_by_code"
    return m.group(1)


def test_joining_grants_viewer_not_member():
    body = _function_body(_SQL)
    assert "'viewer'" in body
    assert "'member'" not in body


def test_expired_codes_are_rejected():
    body = _function_body(_SQL)
    assert "join_code_expires_at" in body
    assert "expired join code" in body


def test_column_is_added_idempotently():
    assert re.search(r"add column if not exists join_code_expires_at", _SQL)


def test_sql_default_matches_python_ttl():
    assert f"interval '{JOIN_CODE_TTL_DAYS} days'" in _SQL


def test_032_runs_after_001_so_its_definition_wins():
    """El arranque re-aplica todas en orden: 001 redefine la función antigua y 032 la pisa."""
    names = sorted(p.name for p in _DIR.glob("*.sql"))
    assert names.index("001_multitenant_kb.sql") < names.index("032_join_code_viewer_expiry.sql")
    later = [n for n in names if n > "032_join_code_viewer_expiry.sql"]
    for name in later:
        assert "join_organization_by_code" not in (_DIR / name).read_text(), name
