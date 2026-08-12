from typing import Any, Dict, List, Optional, Sequence

import psycopg
from pgvector import Vector
from psycopg.rows import dict_row

from src.config import DATABASE_URL, MAX_SEMANTIC_DISTANCE
from src.db.pool import get_pool
from src.defects.embedder import LocalEmbedder

# Los 7 primeros son conocimiento sobre el PRODUCTO y sus fallos. Los 4 últimos son el
# OFICIO del proyecto — lo que se va con el senior y antes no tenía dónde vivir
# (auditoría 12-ago, H3). El CHECK de la BD (migración 027) lleva esta misma lista.
_KINDS = {"regla_negocio", "flujo", "riesgo", "glosario", "leccion", "reto", "patron",
          "runbook", "dato_prueba", "contacto", "decision"}
_STATUSES = {"activo", "obsoleto"}
# Whitelist de columnas editables (los nombres van al SQL → nunca del cliente sin pasar por aquí)
_EDITABLE = ("kind", "title", "challenge", "approach", "outcome", "domain",
             "tags", "project", "status")

KINDS = _KINDS  # export público (el refine valida el kind que propone el LLM)

_INSERT_COLS = ("org_id, kind, title, challenge, approach, outcome, domain, tags, project,"
                " source, confidence, source_url, defect_family_id, run_id, created_by,"
                " embedding")


def embedding_text(title: str, challenge: Optional[str] = None,
                   approach: Optional[str] = None) -> str:
    """Texto que se embebe para la búsqueda semántica (título + reto + enfoque)."""
    return "\n".join(p for p in (title, challenge, approach) if p)


def insert_qa_knowledge(cur, *, org_id: str, kind: str, title: str,
                        challenge: Optional[str], approach: Optional[str],
                        outcome: Optional[str], domain: Optional[str],
                        tags: Optional[Sequence[str]], project: Optional[str],
                        source: str, confidence: str, defect_family_id: Optional[str],
                        run_id: Optional[str], created_by: str, embedding,
                        source_url: Optional[str] = None) -> Dict[str, Any]:
    """INSERT en qa_knowledge sobre un cursor dado. NO hace commit ni comprueba membership:
    lo hace el llamador. Se extrae de create_item para poder insertar dentro de la MISMA
    transacción que la aprobación de una propuesta (atomicidad). Valida el kind."""
    if kind not in _KINDS:
        raise ValueError(f"kind inválido: {kind}")
    cur.execute(
        f"insert into public.qa_knowledge ({_INSERT_COLS})"
        " values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        " returning id, kind, title, domain, tags, confidence, created_at",
        (org_id, kind, title, challenge, approach, outcome, domain, list(tags or []),
         project, source, confidence, source_url, defect_family_id, run_id, created_by,
         embedding),
    )
    return cur.fetchone()


class QaKnowledgeRepository:
    def __init__(self, db_url: str = DATABASE_URL, embedder=None):
        self.db_url = db_url
        self.embedder = embedder or LocalEmbedder()

    def _connect(self) -> psycopg.Connection:
        return get_pool().connection()

    def _is_member(self, cur, org_id: str, user_id: str) -> bool:
        cur.execute("select exists(select 1 from public.memberships"
                    " where org_id=%s and user_id=%s) as ok", (org_id, user_id))
        return bool(cur.fetchone()["ok"])

    def create_item(self, *, user_id: str, org_id: str, kind: str, title: str,
                    challenge: Optional[str] = None, approach: Optional[str] = None,
                    outcome: Optional[str] = None, domain: Optional[str] = None,
                    tags: Optional[Sequence[str]] = None, project: Optional[str] = None,
                    source: str = "manual", confidence: str = "confirmado",
                    defect_family_id: Optional[str] = None, run_id: Optional[str] = None,
                    source_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if kind not in _KINDS:
            raise ValueError(f"kind inválido: {kind}")
        emb = Vector(list(self.embedder.embed(embedding_text(title, challenge, approach))))
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return None
            row = insert_qa_knowledge(
                cur, org_id=org_id, kind=kind, title=title, challenge=challenge,
                approach=approach, outcome=outcome, domain=domain, tags=tags, project=project,
                source=source, confidence=confidence, defect_family_id=defect_family_id,
                run_id=run_id, created_by=user_id, embedding=emb, source_url=source_url,
            )
            conn.commit()
            return dict(row)

    def list_items(self, *, user_id: str, org_id: str, kind: Optional[str] = None,
                   domain: Optional[str] = None, project: Optional[str] = None,
                   status: Optional[str] = None,
                   defect_family_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Hojeo: muestra TODOS los status por defecto (los obsoletos, marcados);
        el filtro de 'solo activos' es cosa de los read-paths de RAG/búsqueda."""
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return []
            q = ("select id, kind, title, challenge, approach, outcome, domain, tags, project,"
                 " source, confidence, source_url, status, created_by, created_at, updated_at"
                 " from public.qa_knowledge where org_id=%s")
            params: list = [org_id]
            if kind:
                q += " and kind=%s"; params.append(kind)
            if domain:
                q += " and domain=%s"; params.append(domain)
            if project:
                q += " and project=%s"; params.append(project)
            if status:
                q += " and status=%s"; params.append(status)
            if defect_family_id:
                q += " and defect_family_id=%s"; params.append(defect_family_id)
            q += " order by created_at desc limit 200"
            cur.execute(q, tuple(params))
            return [dict(r) for r in cur.fetchall()]

    def update_item(self, *, user_id: str, org_id: str, item_id: str,
                    fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Edita un item. Autoridad en el WHERE (estilo CAS, como actions): el AUTOR
        puede editar lo suyo; owner/admin cualquier item de la org. Recalcula el
        embedding si cambia el contenido semántico (title/challenge/approach) — si no,
        la búsqueda semántica serviría vectores obsoletos. El embedding se calcula
        FUERA de la transacción. None = no existe / sin permiso."""
        updates = {k: v for k, v in fields.items() if k in _EDITABLE and v is not None}
        if not updates:
            raise ValueError("nada que actualizar")
        if "kind" in updates and updates["kind"] not in _KINDS:
            raise ValueError(f"kind inválido: {updates['kind']}")
        if "status" in updates and updates["status"] not in _STATUSES:
            raise ValueError(f"status inválido: {updates['status']}")

        current = self.get_item(user_id=user_id, org_id=org_id, item_id=item_id)
        if current is None:
            return None
        emb = None
        if {"title", "challenge", "approach"} & updates.keys():
            merged = {**current, **updates}
            emb = Vector(list(self.embedder.embed(embedding_text(
                merged.get("title") or "", merged.get("challenge"), merged.get("approach")))))

        cols = list(updates.keys())  # nombres de la whitelist _EDITABLE → sin inyección
        set_sql = ", ".join(f"{c}=%s" for c in cols)
        params: List[Any] = [list(updates[c]) if c == "tags" else updates[c] for c in cols]
        if emb is not None:
            set_sql += ", embedding=%s"
            params.append(emb)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"update public.qa_knowledge k set {set_sql}, updated_at=now()"
                " where k.id=%s and k.org_id=%s"
                "   and (k.created_by=%s or exists(select 1 from public.memberships m"
                "     where m.org_id=k.org_id and m.user_id=%s and m.role in ('owner','admin')))"
                " returning id, kind, title, challenge, approach, outcome, domain, tags,"
                " project, source, confidence, status, created_at, updated_at",
                (*params, item_id, org_id, user_id, user_id),
            )
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else None

    def delete_item(self, *, user_id: str, org_id: str, item_id: str) -> bool:
        """Borrado duro (para errores). Misma autoridad que update (autor u owner/admin)."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "delete from public.qa_knowledge k"
                " where k.id=%s and k.org_id=%s"
                "   and (k.created_by=%s or exists(select 1 from public.memberships m"
                "     where m.org_id=k.org_id and m.user_id=%s and m.role in ('owner','admin')))",
                (item_id, org_id, user_id, user_id),
            )
            ok = cur.rowcount > 0
            conn.commit()
        return ok

    def get_item(self, *, user_id: str, org_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return None
            # Columnas explícitas (NUNCA `select *`): el `embedding vector(384)` vuelve
            # como numpy.ndarray y rompe la serialización JSON de la respuesta (500).
            cur.execute(
                "select id, kind, title, challenge, approach, outcome, domain, tags,"
                " project, source, confidence, source_url, defect_family_id, run_id,"
                " created_by, created_at"
                " from public.qa_knowledge where id=%s and org_id=%s",
                (item_id, org_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def search_semantic(self, *, user_id: str, org_id: str,
                        query_embedding: Sequence[float], k: int = 8) -> List[Dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return []
            q = Vector(list(query_embedding))
            # Corte por distancia: sin él, el top-k devolvía ruido cuando no había
            # nada relevante y el LLM respondía desde ese ruido (auditoría 12-ago, H2).
            cur.execute(
                "select id, kind, title, challenge, approach, outcome, domain, confidence"
                " from public.qa_knowledge"
                " where org_id=%s and status = 'activo' and embedding is not null"
                "   and embedding <=> %s < %s"
                " order by embedding <=> %s limit %s",
                (org_id, q, MAX_SEMANTIC_DISTANCE, q, k),
            )
            return [dict(r) for r in cur.fetchall()]
