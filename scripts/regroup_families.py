"""Re-agrupa las familias de defecto con la huella v2 (auditoría 23-nov-2026, #3).

NO se ejecuta solo ni en el arranque. Por defecto es un DRY-RUN que solo informa;
`--apply` escribe. Ejecutarlo contra producción es una decisión de Gonzalo.

Qué hace, por organización y familia:
  1. calcula la huella v2 de cada fallo con lo que hay guardado;
  2. si la familia mezcla varias huellas, deja en ella el grupo MAYOR (conserva su
     etiqueta, razón, lecciones y veredictos) y mueve cada grupo restante a la
     familia de su huella (si ya existe en la org) o a una familia nueva sin
     etiquetar;
  3. actualiza la firma de la familia original a la huella v2 de su grupo, para
     que los runs futuros sigan cayendo en ella; recalcula contadores y centroides.

Límite que no se puede evitar: lo guardado está SANEADO. La huella v2 de la
ingesta sale del texto crudo, así que dos fallos que solo se distinguían por una
URL o una ruta redactadas siguen siendo indistinguibles aquí. Sí se separan los
que mezclaba el nombre del test o un mensaje genérico/vacío (Go `Failed`, Jest).

Etiqueta y razón humanas se quedan en la familia original: el script no puede
saber a qué grupo se referían. Revisa en la UI las familias que informe.

Conexión: DATABASE_URL directo (mismo patrón que scripts/reembed.py). Uso:

    python3 -m scripts.regroup_families              # dry-run: qué partiría
    python3 -m scripts.regroup_families --apply      # escribe
    python3 -m scripts.regroup_families --org <uuid> # solo una org
"""
import argparse
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.defects.fingerprint import fingerprint
from src.ingest.models import FailureRecord


def stored_fingerprint(row: Dict[str, Any]) -> str:
    """Huella v2 de un fallo guardado (texto ya saneado)."""
    return fingerprint(FailureRecord(
        test_name=row.get("test_name") or "", error_type=row.get("error_type"),
        message=row.get("message") or "", trace=row.get("trace"), project="",
        source=row.get("source") or "", file=row.get("file")))


def plan_family(failures: Sequence[Dict[str, Any]]) -> Tuple[str, List[Tuple[str, List[Any]]]]:
    """(huella del grupo que se queda, [(huella, ids de fallo) de los que se van]).
    Puro. El grupo mayor se queda; empate → el de huella menor (determinista)."""
    groups: Dict[str, List[Any]] = defaultdict(list)
    for f in failures:
        groups[stored_fingerprint(f)].append(f["id"])
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    keep_fp = ordered[0][0]
    return keep_fp, [(fp, ids) for fp, ids in ordered[1:]]


_Q_FAMILIES = ("select id, org_id, signature, title from public.defect_families"
               " where scope = 'org' and (%(org)s::uuid is null or org_id = %(org)s) order by id")
_Q_FAILURES = ("select fl.id, fl.test_name, fl.error_type, fl.message, fl.trace, fl.file,"
               " tr.source from public.failures fl join public.test_runs tr on tr.id = fl.run_id"
               " where fl.defect_family_id = %s")
_REFRESH = """
    update public.defect_families f set
        occurrence_count = greatest(1, (select count(*) from public.failures fl
                                        where fl.defect_family_id = f.id)),
        centroid = (select avg(fl.embedding) from public.failures fl
                    where fl.defect_family_id = f.id and fl.embedding is not null)
    where f.id = %s
"""


def _family_for(cur, *, org_id, signature: str, title: str):
    cur.execute("select id from public.defect_families where scope = 'org'"
                " and org_id = %s and signature = %s", (org_id, signature))
    row = cur.fetchone()
    if row:
        return row["id"]
    cur.execute("insert into public.defect_families (scope, org_id, signature, title,"
                " occurrence_count) values ('org', %s, %s, %s, 1) returning id",
                (org_id, signature, title))
    return cur.fetchone()["id"]


def _apply(cur, fam, keep_fp: str, moves) -> None:
    for fp, ids in moves:
        target = _family_for(cur, org_id=fam["org_id"], signature=fp, title=fam["title"])
        cur.execute("update public.failures set defect_family_id = %s, fingerprint = %s"
                    " where id = any(%s)", (target, fp, list(ids)))
        cur.execute(_REFRESH, (target,))
    cur.execute("select exists(select 1 from public.defect_families where scope = 'org'"
                " and org_id = %s and signature = %s and id <> %s) as taken",
                (fam["org_id"], keep_fp, fam["id"]))
    if not cur.fetchone()["taken"]:
        cur.execute("update public.defect_families set signature = %s where id = %s",
                    (keep_fp, fam["id"]))
    cur.execute(_REFRESH, (fam["id"],))


def run(conn, *, org: Optional[str] = None, apply: bool = False) -> int:
    """Devuelve cuántas familias se parten (o se partirían en dry-run)."""
    split = 0
    with conn.cursor() as cur:
        cur.execute(_Q_FAMILIES, {"org": org})
        for fam in cur.fetchall():
            cur.execute(_Q_FAILURES, (fam["id"],))
            failures = cur.fetchall()
            if not failures:
                continue
            keep_fp, moves = plan_family(failures)
            if moves:
                split += 1
                quedan = len(failures) - sum(len(ids) for _, ids in moves)
                print(f"  familia {fam['id']} «{fam['title']}»: se quedan {quedan} fallo(s);"
                      f" salen {len(moves)} grupo(s)", flush=True)
            if apply and (moves or keep_fp != fam["signature"]):
                _apply(cur, fam, keep_fp, moves)
                conn.commit()
    return split


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="escribe (sin él, dry-run)")
    parser.add_argument("--org", default=None, help="limita a una organización (uuid)")
    args = parser.parse_args()

    from scripts.reembed import _connect  # conexión directa con vectores registrados
    if not args.apply:
        print("DRY-RUN: no se escribe nada (usa --apply para re-agrupar).")
    with _connect() as conn:
        n = run(conn, org=args.org, apply=args.apply)
    print(f"OK — familias {'partidas' if args.apply else 'a partir'}: {n}")


if __name__ == "__main__":
    main()
