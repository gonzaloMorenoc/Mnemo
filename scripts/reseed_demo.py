"""Re-seed de la demo: BORRA y re-siembra las orgs demo de un usuario. Uso:

    DATABASE_URL=... python3 scripts/reseed_demo.py <demo_user_uuid>

Pide confirmación explícita (escribir 'reseed') antes de borrar nada."""
import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import psycopg  # noqa: E402

from src.demo.seed import seed_demo  # noqa: E402
from src.demo.seed_continuity import seed_continuity  # noqa: E402
from src.demo.seed_knowledge import seed_knowledge  # noqa: E402

_ORGS = ["Demo MTP", "Cliente Beta"]


def _confirmed(answer: str) -> bool:
    return answer.strip().lower() == "reseed"


def _delete_demo_orgs(db_url: str, demo_user_id: str) -> int:
    """Borra (CASCADE) las orgs demo del usuario. Devuelve cuántas borró."""
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            "delete from public.organizations where created_by=%s and name = any(%s)",
            (demo_user_id, _ORGS),
        )
        n = cur.rowcount
        conn.commit()
    return n


def main(argv, ask=input) -> int:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("DATABASE_URL no definido en el entorno."); return 2
    if len(argv) < 2:
        print("uso: python3 scripts/reseed_demo.py <demo_user_uuid>"); return 2
    demo_user_id = argv[1]
    host = db_url.rsplit("@", 1)[-1] if "@" in db_url else "<oculto>"
    print(f"Esto BORRARÁ las orgs {_ORGS} del usuario {demo_user_id} en {host} y las re-sembrará.")
    if not _confirmed(ask("Escribe 'reseed' para confirmar: ")):
        print("Cancelado."); return 1
    deleted = _delete_demo_orgs(db_url, demo_user_id)
    print(f"Borradas {deleted} orgs. Sembrando…")
    print("seed_demo:", seed_demo(db_url=db_url, demo_user_id=demo_user_id))
    print("seed_knowledge:", seed_knowledge(db_url=db_url, demo_user_id=demo_user_id))
    print("seed_continuity:", seed_continuity(db_url=db_url, demo_user_id=demo_user_id))
    print("Listo.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
