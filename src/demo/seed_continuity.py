"""Siembra del escenario María→Pablo: el oficio de checkout-suite. Idempotente.

A diferencia de seed_knowledge —que exige la org vacía—, esta siembra es
INCREMENTAL: comprueba item a item (por org+kind+title) y añade solo lo que
falta. Por eso puede ejecutarse contra la Demo MTP real sin tocar lo curado a
mano ni las actas ya firmadas, y ejecutarse dos veces sin duplicar nada.
"""
from typing import Any, Dict

import psycopg

from src.demo.continuity_data import CONTINUITY_ITEMS
from src.demo.seed_knowledge import _load_orgs


def seed_continuity(*, db_url: str, demo_user_id: str) -> Dict[str, Any]:
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        orgs = _load_orgs(cur, demo_user_id)
        if "Demo MTP" not in orgs:
            return {"skipped": True,
                    "reason": "ejecuta seed_demo primero (no existe 'Demo MTP')"}
        org_id = orgs["Demo MTP"]
        cur.execute("select kind, title from public.qa_knowledge where org_id=%s",
                    (org_id,))
        existentes = {(kind, title) for kind, title in cur.fetchall()}

    # Import tardío: el embedder carga torch (~segundos) y solo hace falta si
    # hay algo que sembrar.
    from src.defects.embedder import LocalEmbedder
    from src.knowledge.repository import QaKnowledgeRepository

    krepo = QaKnowledgeRepository(db_url, embedder=LocalEmbedder())
    created = 0
    skipped = 0
    por_kind: Dict[str, int] = {}
    for item in CONTINUITY_ITEMS:
        if (item["kind"], item["title"]) in existentes:
            skipped += 1
            continue
        row = krepo.create_item(
            user_id=demo_user_id, org_id=org_id, kind=item["kind"],
            title=item["title"], challenge=item.get("challenge"),
            approach=item.get("approach"), outcome=item.get("outcome"),
            domain=item.get("domain"), tags=item.get("tags"),
            project=item["project"], source="manual", confidence="confirmado",
        )
        if row is not None:
            created += 1
            por_kind[item["kind"]] = por_kind.get(item["kind"], 0) + 1
        else:
            skipped += 1  # no-miembro: no debería pasar con el creador de la org
    return {"created": created, "skipped": skipped, "por_kind": por_kind}
