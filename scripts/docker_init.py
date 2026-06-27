"""Init de la demo on-prem: aplica migraciones, crea el usuario demo via GoTrue y siembra.

Idempotente: re-ejecutar no duplica. Pensado para correr como el servicio `init`.
"""

import glob
import os
import time

import psycopg
import requests

DBURL = os.environ["DATABASE_URL"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_ROLE_KEY = os.environ["SERVICE_ROLE_KEY"]
DEMO_EMAIL = os.environ["DEMO_EMAIL"]
DEMO_PASSWORD = os.environ["DEMO_PASSWORD"]

MIGRATIONS = sorted(glob.glob("db/migrations/*.sql"))


def _wait_db():
    for _ in range(30):
        try:
            with psycopg.connect(DBURL, connect_timeout=3):
                return
        except psycopg.OperationalError:
            time.sleep(2)
    raise SystemExit("db no disponible")


def _apply_migrations():
    with psycopg.connect(DBURL) as conn:
        for path in MIGRATIONS:
            with open(path) as fh:
                sql = fh.read()
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            print(f"migración aplicada: {path}")


def _ensure_demo_user() -> str:
    """Crea (o reutiliza) el usuario demo via la admin API de GoTrue. Devuelve su id."""
    headers = {"apikey": SERVICE_ROLE_KEY, "Authorization": f"Bearer {SERVICE_ROLE_KEY}"}
    resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD, "email_confirm": True},
        headers=headers, timeout=10,
    )
    if resp.status_code in (200, 201):
        return resp.json()["id"]
    # Ya existe: buscarlo
    lst = requests.get(f"{SUPABASE_URL}/auth/v1/admin/users", headers=headers, timeout=10)
    lst.raise_for_status()
    for u in lst.json().get("users", []):
        if u.get("email") == DEMO_EMAIL:
            return u["id"]
    raise SystemExit(f"no se pudo crear/encontrar el usuario demo: {resp.status_code} {resp.text[:200]}")


def _seed(user_id: str):
    from src.defects.embedder import LocalEmbedder
    from src.defects.ingestion_service import IngestionService
    from src.defects.repository import AssuranceRepository
    import json

    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("select id from public.organizations where created_by = %s limit 1", (user_id,))
            row = cur.fetchone()
            if row:
                print("demo ya sembrada; nada que hacer")
                return
            cur.execute(
                "insert into public.organizations (name, created_by) values (%s, %s) returning id",
                ("Demo MTP", user_id),
            )
            org_id = str(cur.fetchone()[0])
        conn.commit()

    repo = AssuranceRepository(DBURL)
    service = IngestionService(repo=repo, embedder=LocalEmbedder())

    def allure(*cases):
        return json.dumps(list(cases)).encode("utf-8")

    def failed(name, message, trace):
        return {"name": name, "status": "failed", "statusDetails": {"message": message, "trace": trace}}

    reports = {
        "cliente-alpha": allure(
            failed("test_login", "TimeoutException: esperando elemento tras 30000ms", "at Login.java:42"),
            failed("test_export", "NullPointerException en ExportService", "at Export.java:11"),
        ),
        "cliente-beta": allure(
            failed("test_checkout", "TimeoutException: esperando elemento tras 12000ms", "at Checkout.java:88"),
        ),
    }
    for project, data in reports.items():
        service.ingest_report(user_id=user_id, org_id=org_id, project=project, source="allure", data=data)
    print(f"demo sembrada: org={org_id} user={user_id}")


def main():
    _wait_db()
    _apply_migrations()
    user_id = _ensure_demo_user()
    _seed(user_id)
    print("init completado")


if __name__ == "__main__":
    main()
