"""Aplica las migraciones pendientes de db/migrations/ (ver src/db/migrate.py).

    DATABASE_URL=... python3 scripts/migrate.py [--baseline-through 030] [--dry-run]

Lo ejecuta el workflow «Desplegar backend» al fusionar en main, antes de reconstruir el
backend; también scripts/docker_init.py. Sale con código 1 si algo falla (el despliegue
se detiene y el backend viejo sigue sirviendo).
"""
import argparse
import logging
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db.migrate import MigrationError, load_migrations, migrate  # noqa: E402

MIGRATIONS_DIR = ROOT / "db" / "migrations"
CONNECT_TIMEOUT_S = 15


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-through", default=os.getenv("MIGRATIONS_BASELINE_THROUGH"),
                        help="en una BD existente sin registro, da por aplicadas las <= este número")
    parser.add_argument("--dry-run", action="store_true", help="solo muestra el plan")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    url = os.getenv("DATABASE_URL")
    if not url:
        logging.error("falta DATABASE_URL")
        return 1
    try:
        with psycopg.connect(url, autocommit=True, connect_timeout=CONNECT_TIMEOUT_S) as conn:
            plan = migrate(conn, load_migrations(MIGRATIONS_DIR),
                           baseline_through=args.baseline_through, dry_run=args.dry_run)
    except MigrationError as exc:
        logging.error("%s", exc)
        return 1
    except psycopg.Error as exc:
        # Sin el mensaje del driver: puede llevar el DSN.
        logging.error("fallo de base de datos: %s", type(exc).__name__)
        return 1
    logging.info("listo: %d pendientes%s", len(plan.pending),
                 " (dry-run, nada aplicado)" if args.dry_run else " aplicadas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
