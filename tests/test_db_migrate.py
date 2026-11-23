"""Runner de migraciones con registro (src/db/migrate.py): plan, baseline y reglas."""
from pathlib import Path

import pytest

from src.db.migrate import (Migration, MigrationError, baseline_entries, build_plan,
                            load_migrations, migrate)

REPO_MIGRATIONS = Path(__file__).resolve().parent.parent / "db" / "migrations"


def _m(name, sql="select 1;"):
    return Migration(name, sql)


MIGS = [_m("001_a.sql"), _m("002_b.sql"), _m("003_c.sql"), _m("999_cierre.sql")]


def test_sin_registro_todo_pendiente_y_la_999_siempre_al_final():
    plan = build_plan(MIGS, {})
    assert [m.filename for m in plan.pending] == ["001_a.sql", "002_b.sql", "003_c.sql"]
    assert [m.filename for m in plan.always] == ["999_cierre.sql"]


def test_solo_aplica_las_no_registradas():
    applied = {m.filename: m.sha256 for m in MIGS[:2]}
    plan = build_plan(MIGS, applied)
    assert [m.filename for m in plan.pending] == ["003_c.sql"]


def test_la_999_se_reaplica_aunque_este_registrada_y_aunque_cambie():
    applied = {m.filename: m.sha256 for m in MIGS[:3]}
    applied["999_cierre.sql"] = "otro-hash"
    plan = build_plan(MIGS, applied)
    assert plan.pending == []
    assert [m.filename for m in plan.always] == ["999_cierre.sql"]


def test_editar_una_migracion_ya_aplicada_es_un_error():
    applied = {"001_a.sql": "hash-antiguo"}
    with pytest.raises(MigrationError, match="001_a.sql"):
        build_plan(MIGS, applied)


def test_baseline_cubre_hasta_el_numero_indicado_y_nunca_la_999():
    names = [m.filename for m in baseline_entries(MIGS, "002")]
    assert names == ["001_a.sql", "002_b.sql"]


def test_los_ficheros_reales_cargan_en_orden_y_la_999_es_la_ultima():
    migs = load_migrations(REPO_MIGRATIONS)
    names = [m.filename for m in migs]
    assert names == sorted(names)
    assert names[-1].startswith("999_")
    assert all(not m.always for m in migs[:-1])


def test_el_baseline_de_produccion_no_deja_fuera_ninguna_anterior_a_030():
    """El workflow usa --baseline-through 030 (estado de prod al crear el registro)."""
    migs = load_migrations(REPO_MIGRATIONS)
    covered = {m.filename for m in baseline_entries(migs, "030")}
    assert len(covered) == 30
    assert "030_triage_corrections_reason_embedding.sql" in covered


def test_migrate_exige_autocommit():
    class _Conn:
        autocommit = False

    with pytest.raises(ValueError, match="autocommit"):
        migrate(_Conn(), MIGS)
