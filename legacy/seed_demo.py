"""Siembra datos de demo de Mnemo en Supabase.

Crea (o reutiliza) un usuario y una org de demo, e ingiere reportes Allure de
ejemplo en 3 proyectos. Dos proyectos comparten un TimeoutException, de modo que
el matching los agrupa en UNA familia de defecto con linaje cross-proyecto.

Uso:
    python scripts/seed_demo.py

Requiere `DATABASE_URL` (Session pooler) en `.env`. La primera ejecución descarga
el modelo de embeddings HuggingFace (perezoso) y puede tardar.
"""

import json
import os
import uuid

import psycopg
from dotenv import load_dotenv

load_dotenv()

from src.defects.embedder import LocalEmbedder  # noqa: E402
from src.defects.ingestion_service import IngestionService  # noqa: E402
from src.defects.repository import AssuranceRepository  # noqa: E402

DBURL = os.getenv("DATABASE_URL", "")


def _allure(*cases: dict) -> bytes:
    return json.dumps(list(cases)).encode("utf-8")


def _failed(name: str, message: str, trace: str) -> dict:
    return {"name": name, "status": "failed", "statusDetails": {"message": message, "trace": trace}}


# project-a y project-b comparten el TimeoutException (misma familia tras matching).
REPORTS = {
    "cliente-alpha": _allure(
        _failed("test_login", "TimeoutException: esperando elemento tras 30000ms", "at Login.java:42"),
        _failed("test_export", "NullPointerException en ExportService", "at Export.java:11"),
    ),
    "cliente-beta": _allure(
        _failed("test_checkout", "TimeoutException: esperando elemento tras 12000ms", "at Checkout.java:88"),
        _failed("test_search", "StaleElementReferenceException en SearchPage", "at Search.java:7"),
    ),
    "cliente-gamma": _allure(
        _failed("test_payment", "AssertionError: esperado 200 pero fue 500", "at Payment.java:21"),
    ),
}


def _create_demo_org() -> tuple[str, str]:
    user_id = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("select set_config('request.jwt.claim.sub', %s, true)", (user_id,))
            cur.execute("select set_config('request.jwt.claim.role', 'authenticated', true)")
            cur.execute(
                """
                insert into auth.users (id, email, role, aud, created_at, updated_at)
                values (%s, %s, 'authenticated', 'authenticated', now(), now())
                on conflict (id) do nothing
                """,
                (user_id, f"demo-{user_id[:8]}@mnemo.local"),
            )
            cur.execute(
                "insert into public.organizations (name, created_by) values (%s, %s) returning id",
                (f"MTP demo {user_id[:6]}", user_id),
            )
            org_id = str(cur.fetchone()[0])
        conn.commit()
    return user_id, org_id


def main() -> None:
    if not DBURL:
        raise SystemExit("DATABASE_URL no configurada (revisa .env, usa el Session pooler).")

    user_id, org_id = _create_demo_org()
    repo = AssuranceRepository(DBURL)
    service = IngestionService(repo=repo, embedder=LocalEmbedder())

    print(f"Org de demo: {org_id} (user {user_id})")
    for project, data in REPORTS.items():
        result = service.ingest_report(
            user_id=user_id, org_id=org_id, project=project, source="allure", data=data
        )
        print(f"  {project}: ingested={result['ingested']} known={result['known']} novel={result['novel']}")

    print("\nFamilias de defecto (Defect DNA):")
    for fam in repo.list_defects(user_id=user_id, org_id=org_id):
        proyectos = ", ".join(fam["projects"])
        print(f"  - {fam['title']}  x{fam['occurrence_count']}  [{proyectos}]")

    print(f"\nListo. Explora el dashboard con esta org. user_id={user_id} org_id={org_id}")


if __name__ == "__main__":
    main()
