"""Runner de migraciones con registro: aplica solo las pendientes, en orden.

Antes se re-aplicaban TODAS las migraciones en cada despliegue (eran idempotentes), con dos
problemas: alguna rehace índices vectoriales en cada pasada, y nada impedía editar una
migración ya aplicada. Ahora cada fichero aplicado queda registrado (nombre + sha256) en
`mnemo_meta.schema_migrations`, fuera de `public` para que la Data API nunca lo vea.

Reglas:
- Las pendientes se aplican en orden de nombre, cada una en su transacción.
- Las que empiezan por ALWAYS_PREFIX (la 999, que cierra la Data API) se re-aplican SIEMPRE
  al final: neutralizan los grants que cualquier migración haya podido conceder.
- Una migración ya aplicada cuyo contenido cambió es un error: se crea otra nueva.
- Baseline: en una BD que ya tenía el esquema antes de existir el registro, las migraciones
  hasta `baseline_through` se dan por aplicadas sin ejecutarlas.
- Un advisory lock impide que dos despliegues migren a la vez.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

ALWAYS_PREFIX = "999_"
# Clave arbitraria pero fija del advisory lock de migraciones.
LOCK_KEY = 7_311_002_301

_CREATE_REGISTRY = """
create schema if not exists mnemo_meta;
revoke all on schema mnemo_meta from public;
create table if not exists mnemo_meta.schema_migrations (
    filename   text primary key,
    sha256     text not null,
    applied_at timestamptz not null default now()
);
"""

# ¿La BD ya tenía el esquema de Mnemo? (para decidir si aplica el baseline)
_HAS_SCHEMA = "select to_regclass('public.organizations') is not null"
_REGISTRY_EXISTS = "select to_regclass('mnemo_meta.schema_migrations') is not null"


class MigrationError(RuntimeError):
    """Estado del registro incompatible con los ficheros (p. ej. migración editada)."""


@dataclass(frozen=True)
class Migration:
    filename: str
    sql: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()

    @property
    def always(self) -> bool:
        return self.filename.startswith(ALWAYS_PREFIX)


@dataclass(frozen=True)
class Plan:
    pending: List[Migration]
    always: List[Migration]


def load_migrations(directory: Path) -> List[Migration]:
    return [Migration(p.name, p.read_text(encoding="utf-8"))
            for p in sorted(directory.glob("*.sql"))]


def build_plan(migrations: Sequence[Migration], applied: Dict[str, str]) -> Plan:
    """Qué aplicar dado lo ya registrado ({filename: sha256}). Pura, sin BD."""
    edited = [m.filename for m in migrations
              if not m.always and m.filename in applied and applied[m.filename] != m.sha256]
    if edited:
        raise MigrationError(
            "migraciones ya aplicadas cuyo contenido ha cambiado: " + ", ".join(edited)
            + ". No se editan: crea una migración nueva.")
    pending = [m for m in migrations if not m.always and m.filename not in applied]
    always = [m for m in migrations if m.always]
    return Plan(pending=pending, always=always)


def baseline_entries(migrations: Sequence[Migration], through: str) -> List[Migration]:
    """Migraciones que el baseline da por aplicadas: prefijo numérico <= `through`."""
    return [m for m in migrations if not m.always and m.filename.split("_", 1)[0] <= through]


def _scalar(cur, sql: str):
    cur.execute(sql)
    return cur.fetchone()[0]


def _record(cur, migration: Migration) -> None:
    cur.execute(
        "insert into mnemo_meta.schema_migrations (filename, sha256) values (%s, %s)"
        " on conflict (filename) do update set sha256 = excluded.sha256, applied_at = now()",
        (migration.filename, migration.sha256))


def _apply(conn, migration: Migration) -> None:
    """Ejecuta y registra en la MISMA transacción: si falla, ni se aplica ni se registra."""
    try:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(migration.sql)
                _record(cur, migration)
    except Exception as exc:
        if type(exc).__name__ == "OperationalError":
            raise  # conexión caída: el mensaje del driver puede llevar el DSN
        raise MigrationError(f"{migration.filename} falló: {exc}") from exc
    logger.info("migración aplicada: %s", migration.filename)


def _registry_exists(conn) -> bool:
    with conn.cursor() as cur:
        return bool(_scalar(cur, _REGISTRY_EXISTS))


def _baseline_applies(conn, baseline_through: Optional[str]) -> bool:
    """Solo en una BD que ya tenía el esquema y aún no tenía registro."""
    if not baseline_through or _registry_exists(conn):
        return False
    with conn.cursor() as cur:
        return bool(_scalar(cur, _HAS_SCHEMA))


def _ensure_registry(conn, migrations: Sequence[Migration],
                     baseline_through: Optional[str]) -> None:
    do_baseline = _baseline_applies(conn, baseline_through)
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(_CREATE_REGISTRY)
            if not do_baseline:
                return
            entries = baseline_entries(migrations, baseline_through)
            for m in entries:
                _record(cur, m)
    logger.info("baseline: %d migraciones (<= %s) dadas por aplicadas",
                len(entries), baseline_through)


def _applied(conn) -> Dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("select filename, sha256 from mnemo_meta.schema_migrations")
        return {row[0]: row[1] for row in cur.fetchall()}


def _applied_without_writing(conn, migrations: Sequence[Migration],
                             baseline_through: Optional[str]) -> Dict[str, str]:
    """Lo que estaría registrado, sin crear nada (para --dry-run)."""
    if _registry_exists(conn):
        return _applied(conn)
    if _baseline_applies(conn, baseline_through):
        return {m.filename: m.sha256 for m in baseline_entries(migrations, baseline_through)}
    return {}


def migrate(conn, migrations: Sequence[Migration], *,
            baseline_through: Optional[str] = None, dry_run: bool = False) -> Plan:
    """Aplica lo pendiente y re-aplica las «always».

    `conn` debe estar en autocommit: cada migración abre su propia transacción real
    (con autocommit=False un select previo la convertiría en un savepoint)."""
    if not conn.autocommit:
        raise ValueError("migrate() necesita una conexión con autocommit=True")
    if dry_run:
        plan = build_plan(migrations, _applied_without_writing(conn, migrations, baseline_through))
        _log_plan(plan)
        return plan
    with conn.cursor() as cur:
        cur.execute("select pg_advisory_lock(%s)", (LOCK_KEY,))
    try:
        _ensure_registry(conn, migrations, baseline_through)
        plan = build_plan(migrations, _applied(conn))
        _log_plan(plan)
        for migration in [*plan.pending, *plan.always]:
            _apply(conn, migration)
        return plan
    finally:
        with conn.cursor() as cur:
            cur.execute("select pg_advisory_unlock(%s)", (LOCK_KEY,))


def _log_plan(plan: Plan) -> None:
    logger.info("pendientes: %s · siempre: %s",
                [m.filename for m in plan.pending] or "ninguna",
                [m.filename for m in plan.always] or "ninguna")
