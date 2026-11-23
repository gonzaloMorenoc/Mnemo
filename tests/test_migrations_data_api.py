"""La Data API de Supabase (PostgREST) debe quedar cerrada tras aplicar las migraciones.

El despliegue re-aplica TODAS las migraciones en orden y varias antiguas conceden permisos a
`authenticated`. La 999 los retira cada vez, así que tiene que ser siempre la última y
cubrir tablas, secuencias, funciones y privilegios por defecto (auditoría 23-nov-2026, #1).
"""
from pathlib import Path
import re

MIGRATIONS = Path(__file__).resolve().parent.parent / "db" / "migrations"
CLOSING = "999_cerrar_data_api.sql"


def _sql_files():
    return sorted(p.name for p in MIGRATIONS.glob("*.sql"))


def _closing_sql():
    return (MIGRATIONS / CLOSING).read_text(encoding="utf-8").lower()


def test_la_migracion_de_cierre_es_la_ultima_en_aplicarse():
    assert _sql_files()[-1] == CLOSING


def test_retira_tablas_y_secuencias_a_anon_y_authenticated():
    sql = _closing_sql()
    assert "revoke all on all tables in schema public from anon, authenticated" in sql
    assert "revoke all on all sequences in schema public from anon, authenticated" in sql


def test_retira_execute_de_las_funciones_propias_tambien_a_public():
    sql = _closing_sql()
    assert re.search(r"revoke execute on function %s from public, anon, authenticated", sql)


def test_los_objetos_futuros_no_nacen_expuestos():
    sql = _closing_sql()
    assert "alter default privileges in schema public revoke all on tables from anon, authenticated" in sql
    assert "alter default privileges revoke execute on functions from public" in sql


def test_ninguna_migracion_concede_a_anon():
    """anon nunca ha necesitado nada: un grant nuevo a anon es casi seguro un error."""
    offenders = [
        name for name in _sql_files()
        if re.search(r"\bgrant\b[^;]*\bto\b[^;]*\banon\b",
                     (MIGRATIONS / name).read_text(encoding="utf-8").lower())
    ]
    assert offenders == []
