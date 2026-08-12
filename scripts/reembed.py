"""Re-embebe TODO el contenido vectorial con el EMBEDDING_MODEL configurado.

Por qué existe: al cambiar de modelo de embeddings (p. ej. al multilingüe,
auditoría 12-ago-2026 H2), los vectores viejos y los nuevos viven en espacios
distintos — el coseno entre ellos no significa nada. Sin re-embeber:
  - la búsqueda semántica devuelve basura (y el corte MAX_SEMANTIC_DISTANCE
    puede filtrarlo TODO),
  - el merge de familias (decide_match, coseno >= 0.85 contra el centroide)
    deja de agrupar y fragmenta familias nuevas.

Qué re-embebe (todas las columnas vector(384) del API v2):
  - public.failures.embedding        ← f"{error_type} {message}" (misma receta
                                        que la ingesta: ingestion_service.py)
  - public.defect_families.centroid  ← media de los embeddings nuevos de sus
                                        fallos (familias sin fallos: centroide
                                        a NULL, dejan de participar en el match)
  - public.qa_knowledge.embedding    ← embedding_text(title, challenge, approach)
  - public.test_assets.embedding     ← content

No toca las tablas del RAG v1 legacy (documents/chunks de 001): están fuera
del arranque de producción (ver asgi.py).

Conexión: DATABASE_URL directo (el rol del pooler hace BYPASS de RLS — mismo
patrón que scripts/reseed_demo.py). Idempotente: re-ejecutarlo solo re-embebe
otra vez. Uso:

    python3 -m scripts.reembed            # todo
    python3 -m scripts.reembed --dry-run  # solo contar, sin escribir
"""
import argparse
import sys

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from src.config import DATABASE_URL, EMBEDDING_MODEL
from src.defects.embedder import LocalEmbedder
from src.knowledge.repository import embedding_text

_BATCH = 200  # filas por lote: acota memoria y tamaño de transacción


def _connect() -> psycopg.Connection:
    if not DATABASE_URL:
        sys.exit("DATABASE_URL no configurada — nada que re-embeber.")
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    # Imprescindible para ESCRIBIR vectores: sin el adaptador registrado, psycopg
    # no sabe pasar un Vector como parámetro y el primer UPDATE muere con
    # "cannot adapt type 'Vector'". El código de producción lo registra en el
    # configure del pool (src/db/pool.py); aquí conectamos sin pool a propósito
    # (bypass de RLS), así que hay que registrarlo a mano.
    register_vector(conn)
    return conn


def _count(cur, sql: str, params=()) -> int:
    cur.execute(sql, params)
    return cur.fetchone()["n"]


def reembed_failures(conn, embedder, *, dry_run: bool) -> int:
    """failures.embedding — misma receta de texto que la ingesta."""
    with conn.cursor() as cur:
        total = _count(cur, "select count(*) as n from public.failures")
        if dry_run:
            return total
        done = 0
        last_id = None
        while True:
            # Paginación por id (estable frente a updates de la propia pasada)
            cur.execute(
                "select id, error_type, message from public.failures"
                " where (%s::uuid is null or id > %s) order by id limit %s",
                (last_id, last_id, _BATCH))
            rows = cur.fetchall()
            if not rows:
                break
            for r in rows:
                text = f"{r['error_type'] or ''} {r['message'] or ''}".strip()
                emb = Vector(list(embedder.embed(text))) if text else None
                cur.execute("update public.failures set embedding=%s where id=%s",
                            (emb, r["id"]))
            conn.commit()
            done += len(rows)
            last_id = rows[-1]["id"]
            print(f"  failures: {done}/{total}", flush=True)
        return done


def recompute_centroids(conn, *, dry_run: bool) -> int:
    """defect_families.centroid = media de los embeddings (ya nuevos) de sus fallos.

    100% SQL (pgvector avg). Ejecutar SIEMPRE DESPUÉS de reembed_failures."""
    with conn.cursor() as cur:
        total = _count(cur, "select count(*) as n from public.defect_families")
        if dry_run:
            return total
        cur.execute(
            "update public.defect_families f set centroid = sub.c"
            " from (select defect_family_id, avg(embedding) as c from public.failures"
            "       where defect_family_id is not null and embedding is not null"
            "       group by defect_family_id) sub"
            " where sub.defect_family_id = f.id")
        n_con_fallos = cur.rowcount
        # Familias sin fallos con embedding: centroide viejo = espacio viejo → fuera.
        cur.execute(
            "update public.defect_families f set centroid = null"
            " where f.centroid is not null and not exists ("
            "   select 1 from public.failures fl"
            "   where fl.defect_family_id = f.id and fl.embedding is not null)")
        conn.commit()
        print(f"  centroides: {n_con_fallos} recalculados, {cur.rowcount} anulados", flush=True)
        return n_con_fallos


def reembed_qa_knowledge(conn, embedder, *, dry_run: bool) -> int:
    with conn.cursor() as cur:
        total = _count(cur, "select count(*) as n from public.qa_knowledge")
        if dry_run:
            return total
        cur.execute("select id, title, challenge, approach from public.qa_knowledge order by id")
        rows = cur.fetchall()
        for i, r in enumerate(rows, 1):
            emb = Vector(list(embedder.embed(
                embedding_text(r["title"] or "", r["challenge"], r["approach"]))))
            cur.execute("update public.qa_knowledge set embedding=%s where id=%s",
                        (emb, r["id"]))
            if i % _BATCH == 0:
                conn.commit()
                print(f"  qa_knowledge: {i}/{total}", flush=True)
        conn.commit()
        return len(rows)


def reembed_test_assets(conn, embedder, *, dry_run: bool) -> int:
    with conn.cursor() as cur:
        total = _count(cur, "select count(*) as n from public.test_assets")
        if dry_run:
            return total
        cur.execute("select id, content from public.test_assets order by id")
        rows = cur.fetchall()
        for i, r in enumerate(rows, 1):
            emb = Vector(list(embedder.embed(r["content"] or "")))
            cur.execute("update public.test_assets set embedding=%s where id=%s",
                        (emb, r["id"]))
            if i % _BATCH == 0:
                conn.commit()
                print(f"  test_assets: {i}/{total}", flush=True)
        conn.commit()
        return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="solo contar filas afectadas, sin escribir")
    args = parser.parse_args()

    print(f"Modelo: {EMBEDDING_MODEL}")
    embedder = LocalEmbedder()
    # Falla AQUÍ (antes de tocar la BD) si el modelo no carga o no es 384-dim.
    dims = len(embedder.embed("sonda"))
    if dims != 384:
        sys.exit(f"El modelo produce {dims} dims y el esquema es vector(384). Abortado.")

    with _connect() as conn:
        modo = "DRY-RUN (sin escribir)" if args.dry_run else "re-embebiendo"
        print(f"{modo}…")
        n_f = reembed_failures(conn, embedder, dry_run=args.dry_run)
        n_c = recompute_centroids(conn, dry_run=args.dry_run)
        n_k = reembed_qa_knowledge(conn, embedder, dry_run=args.dry_run)
        n_t = reembed_test_assets(conn, embedder, dry_run=args.dry_run)
    print(f"OK — failures={n_f} centroides={n_c} qa_knowledge={n_k} test_assets={n_t}")


if __name__ == "__main__":
    main()
