"""La siembra de riqueza: semanal-idempotente, triaje solo de unknown, protegidos intactos."""
import os
import uuid
from datetime import date

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv()

from src.demo.seed_riqueza import seed_riqueza, week_uids  # noqa: E402

DBURL = os.getenv("DATABASE_URL", "")


def test_week_uids_deterministas_y_acotados():
    uids = week_uids("tienda-online", start=date(2026, 7, 23), until=date(2026, 8, 13))
    assert uids[0][0] == "riqueza-tienda-online-2026-W30"
    assert len(uids) == 4                       # W30..W33
    assert uids == week_uids("tienda-online", start=date(2026, 7, 23), until=date(2026, 8, 13))


def test_week_uids_no_fecha_en_el_futuro():
    # El run de la semana en curso se fecha como muy tarde en `until`, nunca después.
    uids = week_uids("api-pagos", start=date(2026, 8, 10), until=date(2026, 8, 11))
    assert all(fecha <= date(2026, 8, 11) for _, fecha in uids)


@pytest.fixture()
def org_riqueza():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                    " values (%s,%s,'authenticated','authenticated',now(),now())",
                    (user, f"riq-{user[:8]}@test.internal"))
        cur.execute("insert into public.organizations (name, created_by)"
                    " values ('Demo MTP',%s) returning id", (user,))
        org = str(cur.fetchone()[0])
        conn.commit()
    yield {"org": org, "user": user}
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("delete from public.organizations where id=%s", (org,))
        cur.execute("delete from auth.users where id=%s", (user,))
        conn.commit()


@pytest.mark.integration
def test_siembra_y_reejecucion_semanal(org_riqueza):
    """Primera pasada crea runs; la segunda con el MISMO tope no crea ninguno
    (dedup por run_uid); con tope una semana más tarde crea solo la semana nueva."""
    out1 = seed_riqueza(db_url=DBURL, demo_user_id=org_riqueza["user"],
                        until=date(2026, 8, 13))
    assert out1["runs_creados"] > 0
    out2 = seed_riqueza(db_url=DBURL, demo_user_id=org_riqueza["user"],
                        until=date(2026, 8, 13))
    assert out2["runs_creados"] == 0
    out3 = seed_riqueza(db_url=DBURL, demo_user_id=org_riqueza["user"],
                        until=date(2026, 8, 20))
    assert out3["runs_creados"] == 6            # una semana nueva × 6 proyectos


def _par_de_firma_efimero() -> "tuple[str, str]":
    """Par Ed25519 de usar y tirar: el .env local NO tiene la privada real de
    prod (placeholder), y el test no debe depender de secretos del despliegue."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()).decode()
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv_pem, pub_pem


@pytest.mark.integration
def test_todos_los_runs_quedan_con_acta_y_veredicto(org_riqueza):
    """Sin acta no hay veredicto en el dashboard: la siembra debe dejar cada run
    certificado (triaje del motor incluido) y ser idempotente en la segunda pasada."""
    priv, pub = _par_de_firma_efimero()
    out1 = seed_riqueza(db_url=DBURL, demo_user_id=org_riqueza["user"],
                        until=date(2026, 8, 13),
                        signing_private_key=priv, signing_public_key=pub)
    assert out1["actas"] > 0
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("select count(*) from public.test_runs tr"
                    " where tr.org_id=%s and not exists"
                    "  (select 1 from public.certificates c where c.run_id=tr.id)",
                    (org_riqueza["org"],))
        assert cur.fetchone()[0] == 0           # ningún run sin acta
        cur.execute("select count(*) from public.certificates"
                    " where org_id=%s and verdict is not null", (org_riqueza["org"],))
        assert cur.fetchone()[0] == out1["actas"]
    out2 = seed_riqueza(db_url=DBURL, demo_user_id=org_riqueza["user"],
                        until=date(2026, 8, 13),
                        signing_private_key=priv, signing_public_key=pub)
    assert out2["actas"] == 0                   # re-ejecutar no duplica actas


@pytest.mark.integration
def test_los_protegidos_no_ganan_fallos_ni_kb(org_riqueza):
    seed_riqueza(db_url=DBURL, demo_user_id=org_riqueza["user"], until=date(2026, 8, 13))
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("select count(*) from public.failures fl"
                    " join public.test_runs tr on tr.id=fl.run_id"
                    " where tr.org_id=%s and tr.project in ('checkout-suite','banca-movil')",
                    (org_riqueza["org"],))
        assert cur.fetchone()[0] == 0
        cur.execute("select count(*) from public.qa_knowledge"
                    " where org_id=%s and project in ('checkout-suite','banca-movil')",
                    (org_riqueza["org"],))
        assert cur.fetchone()[0] == 0
