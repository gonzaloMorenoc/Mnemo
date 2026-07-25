"""Siembra la capa de CONOCIMIENTO de la demo sobre las orgs de seed_demo.

Puebla lo que seed_demo no toca: memoria QA (los 7 kinds, con enlaces a las
familias reales → grafo), causas raíz, etiquetado de familias (calibración
viva) y test assets (automation/gaps). Org B recibe su propio corpus para que
el aislamiento se demuestre con contenido.

Idempotente: si Org A ya tiene items de conocimiento devuelve {"skipped": True}.
Requiere haber ejecutado seed_demo antes (usa sus orgs y familias).
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

import psycopg

from src.demo.knowledge_data import (
    FAMILY_LABELS,
    KNOWLEDGE_ORG_A,
    KNOWLEDGE_ORG_B,
    PROJECT,
    PROPUESTAS,
    ROOT_CAUSES,
    TEST_ASSETS,
)

_DEMO_REPO = "demo/checkout-suite"


def _find_family(families: List[Dict[str, Any]], keywords: Sequence[str]) -> Optional[str]:
    """Primera familia cuyo material (título + tests + mensaje) contiene alguna keyword.

    Los títulos de familia son el error_type ("TimeoutError"), así que el matching
    útil está en los test_name y mensajes de sus fallos."""
    for fam in families:
        haystack = (fam["haystack"] or "").lower()
        if any(kw.lower() in haystack for kw in keywords):
            return str(fam["id"])
    return None


def _load_orgs(cur, demo_user_id: str) -> Dict[str, str]:
    cur.execute(
        "select id, name from public.organizations"
        " where created_by = %s and name in ('Demo MTP', 'Cliente Beta')",
        (demo_user_id,),
    )
    return {name: str(oid) for oid, name in cur.fetchall()}


def seed_knowledge(*, db_url: str, demo_user_id: str) -> Dict[str, Any]:
    """Puebla conocimiento + causas raíz + calibración + assets. Idempotente.

    Devuelve {"skipped": True, "reason": ...} si falta el seed base o si ya
    hay conocimiento sembrado; si no, un resumen con contadores.
    """
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            orgs = _load_orgs(cur, demo_user_id)
            if "Demo MTP" not in orgs:
                return {"skipped": True, "reason": "ejecuta seed_demo primero (no existe 'Demo MTP')"}
            org_a = orgs["Demo MTP"]
            org_b = orgs.get("Cliente Beta")

            cur.execute("select count(*) from public.qa_knowledge where org_id = %s", (org_a,))
            if cur.fetchone()[0] > 0:
                return {"skipped": True, "reason": "Org A ya tiene conocimiento sembrado"}

            cur.execute(
                "select df.id,"
                "       concat_ws(' ', df.title,"
                "                 string_agg(distinct fl.test_name, ' '),"
                "                 max(fl.message)) as haystack"
                " from public.defect_families df"
                " left join public.failures fl on fl.defect_family_id = df.id"
                " where df.org_id = %s"
                " group by df.id, df.title, df.first_seen"
                " order by df.first_seen",
                (org_a,),
            )
            families = [{"id": r[0], "haystack": r[1]} for r in cur.fetchall()]

    # Servicios reales (mismos que la API) — el embedder da la búsqueda semántica.
    from src.defects.embedder import LocalEmbedder
    from src.defects.repository import AssuranceRepository
    from src.knowledge.repository import QaKnowledgeRepository
    from src.repo_ingest.repository import TestAssetRepository

    embedder = LocalEmbedder()
    krepo = QaKnowledgeRepository(db_url, embedder=embedder)
    arepo = AssuranceRepository(db_url)
    assets_repo = TestAssetRepository(db_url, embedder=embedder)

    def _create_items(org_id: str, items: List[Dict[str, Any]]) -> int:
        count = 0
        for item in items:
            fam_id = None
            keywords: Tuple[str, ...] = tuple(item.get("family_keywords") or ())
            if keywords:
                fam_id = _find_family(families, keywords)
            created = krepo.create_item(
                user_id=demo_user_id,
                org_id=org_id,
                kind=item["kind"],
                title=item["title"],
                challenge=item.get("challenge"),
                approach=item.get("approach"),
                outcome=item.get("outcome"),
                domain=item.get("domain"),
                tags=item.get("tags"),
                project=item.get("project", PROJECT),
                source=item.get("source", "manual"),
                confidence=item.get("confidence", "confirmado"),
                defect_family_id=fam_id,
            )
            if created is not None:
                count += 1
        return count

    items_a = _create_items(org_a, KNOWLEDGE_ORG_A)
    items_b = _create_items(org_b, KNOWLEDGE_ORG_B) if org_b else 0

    root_causes = 0
    for keywords, texto in ROOT_CAUSES:
        fam_id = _find_family(families, keywords)
        if fam_id and arepo.save_root_cause(user_id=demo_user_id, defect_id=fam_id, text=texto):
            root_causes += 1

    labels = 0
    for keywords, label, reason in FAMILY_LABELS:
        fam_id = _find_family(families, keywords)
        if fam_id and arepo.set_family_label(
            user_id=demo_user_id, family_id=fam_id, label=label, reason=reason
        ):
            labels += 1

    assets = assets_repo.replace_for_repo(
        user_id=demo_user_id, org_id=org_a, repo=_DEMO_REPO, assets=TEST_ASSETS
    )

    # Propuestas PENDIENTES: el lazo del producto es que el sistema proponga una
    # lección y una persona la apruebe. Con la bandeja vacía ese paso no se ve.
    propuestas = 0
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        for prop in PROPUESTAS:
            fam_id = _find_family(families, tuple(prop.get("family_keywords") or ()))
            cur.execute(
                "insert into public.knowledge_proposals"
                " (org_id, defect_family_id, kind, title, challenge, approach, domain,"
                "  outcome, tags, status, created_by)"
                " values (%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s)",
                (org_a, fam_id, prop["kind"], prop["title"], prop.get("challenge"),
                 prop.get("approach"), prop.get("domain"), prop.get("outcome"),
                 prop.get("tags") or [], demo_user_id),
            )
            propuestas += 1
        conn.commit()

    return {
        "propuestas": propuestas,
        "org_a": org_a,
        "org_b": org_b,
        "knowledge_org_a": items_a,
        "knowledge_org_b": items_b,
        "root_causes": root_causes,
        "family_labels": labels,
        "test_assets": assets,
    }
