"""El CHECK de certificates.verdict debe admitir TODOS los veredictos del motor.

Protege del drift código↔BD: el rename inconcluso→sin_confirmar (PR #95) entró en
el motor sin migración del CHECK, y cada acta `sin_confirmar` moría en el INSERT
con CheckViolation (502 al certificar). Migración 029.
"""
import os

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv()

DBURL = os.getenv("DATABASE_URL", "")


@pytest.mark.integration
def test_check_de_verdict_admite_todos_los_veredictos_del_motor():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    from src.certify.gate import _MOTIVO
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute(
            "select pg_get_constraintdef(oid) from pg_constraint"
            " where conrelid='public.certificates'::regclass"
            "   and conname='certificates_verdict_check'")
        row = cur.fetchone()
    assert row, "el CHECK certificates_verdict_check no existe"
    for verdict in _MOTIVO:
        assert f"'{verdict}'" in row[0], (
            f"el motor emite '{verdict}' pero el CHECK vivo no lo admite: el INSERT"
            " del acta muere con CheckViolation (aplicar db/migrations/029)")
