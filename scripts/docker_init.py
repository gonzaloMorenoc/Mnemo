"""Init de la demo on-prem: aplica migraciones, crea el usuario demo via GoTrue y siembra.

Idempotente: re-ejecutar no duplica. Pensado para correr como el servicio `init`.
"""

import glob
import os
import sys
import time
from pathlib import Path

import psycopg
import requests
from dotenv import load_dotenv

# Ejecutable como `python3 scripts/docker_init.py` desde cualquier cwd:
# ancla la raíz del repo para el import de `src` y para el glob de migraciones,
# y carga el .env (mismo bootstrap que scripts/eval_ai.py).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

DBURL = os.environ["DATABASE_URL"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_ROLE_KEY = os.environ["SERVICE_ROLE_KEY"]
DEMO_EMAIL = os.environ["DEMO_EMAIL"]
DEMO_PASSWORD = os.environ["DEMO_PASSWORD"]

MIGRATIONS = sorted(glob.glob(str(ROOT / "db" / "migrations" / "*.sql")))


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
    from src.demo.seed import seed_demo
    summary = seed_demo(db_url=DBURL, demo_user_id=user_id)
    print(f"demo sembrada: {summary}")


def main():
    _wait_db()
    _apply_migrations()
    user_id = _ensure_demo_user()
    _seed(user_id)
    print("init completado")


if __name__ == "__main__":
    main()
