"""La 036 sobre una BD CON DATOS, como en producción (el job de CI parte de una vacía).

Crea una base temporal en el Postgres de PRUEBA (MNEMO_TEST_DATABASE_URL, nunca
DATABASE_URL), aplica las migraciones anteriores a la 036, siembra casos límite y
aplica el resto. Comprueba también que el código ANTERIOR (que no sabe de `projects`)
sigue escribiendo, porque las migraciones se aplican antes de reconstruir el backend.
"""
import os
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from src.db.migrate import load_migrations, migrate

pytestmark = [pytest.mark.integration, pytest.mark.testdb]
DBURL = os.getenv("MNEMO_TEST_DATABASE_URL", "")
ROOT = Path(__file__).resolve().parent.parent
USER = "00000000-0000-4000-8000-0000000000a1"
ORG = "00000000-0000-4000-8000-0000000000b1"
LONG_KEY = "p" * 600


@pytest.fixture
def scratch_db():
    if not DBURL:
        pytest.skip("MNEMO_TEST_DATABASE_URL no configurada")
    name = f"mig036_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(DBURL, autocommit=True) as admin:
        admin.execute(f'create database "{name}"')
    url = make_conninfo(DBURL, dbname=name)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute((ROOT / "scripts/ci/bootstrap_test_db.sql").read_text(encoding="utf-8"))
    yield url
    with psycopg.connect(DBURL, autocommit=True) as admin:
        admin.execute(f'drop database if exists "{name}" with (force)')


def _migrate(url, migrations):
    with psycopg.connect(url, autocommit=True) as conn:
        migrate(conn, migrations)


def test_036_con_datos_y_casos_limite(scratch_db):
    all_migrations = load_migrations(ROOT / "db" / "migrations")
    _migrate(scratch_db, [m for m in all_migrations if m.filename < "036"])

    with psycopg.connect(scratch_db) as conn, conn.cursor() as cur:
        cur.execute("insert into auth.users (id, email) values (%s, 'a@t.local')", (USER,))
        cur.execute("insert into public.organizations (id, name, created_by) values (%s,'Org',%s)",
                    (ORG, USER))
        for project in ("checkout-suite", "   ", "", LONG_KEY):
            cur.execute("insert into public.test_runs (org_id, project, source)"
                        " values (%s,%s,'junit')", (ORG, project))
        for project in ("   ", None, "banca-movil"):
            cur.execute("insert into public.qa_knowledge (org_id, kind, title, project, created_by)"
                        " values (%s,'leccion','t',%s,%s)", (ORG, project, USER))
        conn.commit()

    _migrate(scratch_db, all_migrations)            # 036 + 999 sobre los datos

    with psycopg.connect(scratch_db) as conn, conn.cursor() as cur:
        cur.execute("select key, name from public.projects where org_id = %s order by key", (ORG,))
        projects = dict(cur.fetchall())
        assert set(projects) == {"", "   ", "banca-movil", "checkout-suite", LONG_KEY}
        assert projects[""] == "(sin nombre)" and projects["   "] == "(sin nombre)"
        assert projects[LONG_KEY] == "p" * 200
        cur.execute("select count(*) from public.qa_knowledge where project is null")
        assert cur.fetchone()[0] == 2               # el blanco pasa a «toda la organización»

        # El código anterior sigue escribiendo: proyecto nuevo, sin tocar `projects`.
        cur.execute("insert into public.test_runs (org_id, project, source)"
                    " values (%s,'nuevo-del-ci','junit')", (ORG,))
        cur.execute("insert into public.qa_knowledge (org_id, kind, title, project, created_by)"
                    " values (%s,'leccion','x','  ',%s) returning project", (ORG, USER))
        assert cur.fetchone()[0] is None
        cur.execute("update public.qa_knowledge set project = 'otro' where title = 'x'")
        cur.execute("select count(*) from public.projects where key in ('nuevo-del-ci', 'otro')")
        assert cur.fetchone()[0] == 2

        # Borrar la organización arrastra proyectos y datos sin chocar con la FK.
        cur.execute("delete from public.organizations where id = %s", (ORG,))
        cur.execute("select count(*) from public.projects")
        assert cur.fetchone()[0] == 0
        conn.commit()


def test_la_api_no_puede_crear_lo_que_la_migracion_tolera():
    """Las claves NUEVAS sí se validan (en la API): una línea, 1-200 caracteres."""
    from pydantic import ValidationError

    from src.projects.api import ProjectCreate
    for bad in ("", "   ", "a\nb", "x" * 201):
        with pytest.raises(ValidationError):
            ProjectCreate(org_id="o", key=bad)
