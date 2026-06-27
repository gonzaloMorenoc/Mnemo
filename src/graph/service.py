from typing import Any, Dict, List, Optional
import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from src.config import DATABASE_URL


class GraphService:
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url

    def _connect(self):
        conn = psycopg.connect(self.db_url, row_factory=dict_row)
        register_vector(conn)
        return conn

    def _is_member(self, cur, org_id: str, user_id: str) -> bool:
        cur.execute("select exists(select 1 from public.memberships"
                    " where org_id=%s and user_id=%s) as ok", (org_id, user_id))
        return bool(cur.fetchone()["ok"])

    def build_graph(self, *, user_id: str, org_id: str, focus: Optional[str] = None,
                    limit: int = 200) -> Dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return {"nodes": [], "edges": []}
            cur.execute(
                "select id::text, kind, title, domain, tags, defect_family_id::text"
                " from public.qa_knowledge where org_id=%s order by created_at desc limit %s",
                (org_id, limit))
            krows = cur.fetchall()
            fam_ids = [r["defect_family_id"] for r in krows if r["defect_family_id"]]
            fams = {}
            if fam_ids:
                cur.execute("select id::text, title, occurrence_count from public.defect_families"
                            " where id = any(%s::uuid[]) and (org_id=%s or scope='global')",
                            (fam_ids, org_id))
                fams = {r["id"]: r for r in cur.fetchall()}
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, str]] = []

        def add_node(nid, ntype, label, **extra):
            if nid not in nodes:
                nodes[nid] = {"id": nid, "type": ntype, "label": label, **extra}

        for k in krows:
            add_node(k["id"], "knowledge", k["title"], kind=k["kind"], domain=k.get("domain"))
            if k.get("domain"):
                dom = f"domain:{k['domain']}"
                add_node(dom, "domain", k["domain"])
                edges.append({"source": k["id"], "target": dom, "relation": "pertenece"})
            fid = k.get("defect_family_id")
            if fid and fid in fams:
                add_node(fid, "defect", fams[fid]["title"], count=fams[fid]["occurrence_count"])
                edges.append({"source": k["id"], "target": fid, "relation": "documenta"})
        # tag edges: knowledge que comparten un tag
        by_tag: Dict[str, List[str]] = {}
        for k in krows:
            for t in (k.get("tags") or []):
                by_tag.setdefault(t, []).append(k["id"])
        for ids in by_tag.values():
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    edges.append({"source": ids[i], "target": ids[j], "relation": "tag"})

        if focus:
            keep = {focus} | {e["target"] for e in edges if e["source"] == focus} \
                            | {e["source"] for e in edges if e["target"] == focus}
            nodes = {nid: n for nid, n in nodes.items() if nid in keep}
            edges = [e for e in edges if e["source"] in keep and e["target"] in keep]
        return {"nodes": list(nodes.values()), "edges": edges}
