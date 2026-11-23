from typing import Any, Dict, List, Optional

from src.ai import nl_query
from src.defects.embedder import get_shared_embedder
from src.knowledge.ranking import merge_by_relevance

# Claves internas del ranking que no salen de la búsqueda (la distancia sale como
# `score` = 1 - distancia, más fácil de leer: mayor = más relevante).
_INTERNAL_KEYS = ("dist", "priority")


class KnowledgeService:
    def __init__(self, knowledge_repo, assurance_repo, embedder=None):
        self.knowledge = knowledge_repo
        self.assurance = assurance_repo
        self.embedder = embedder or get_shared_embedder()

    def search_unified(self, *, user_id: str, org_id: str, query: str, k: int = 8,
                       project: Optional[str] = None) -> List[Dict[str, Any]]:
        """Conocimiento + familias, mezclados por relevancia (ranking.merge_by_relevance).
        Con `project`: lo del proyecto + lo de toda la org, y familias con fallos en él."""
        emb = self.embedder.embed(query)
        items = self.knowledge.search_semantic(user_id=user_id, org_id=org_id, query_embedding=emb,
                                               k=k, project=project)
        fams = self.assurance.search_families_semantic(user_id=user_id, org_id=org_id,
                                                       query_embedding=emb, k=k, project=project)
        knowledge = [{"id": str(i["id"]), "type": "knowledge", "title": i.get("title"),
                      "content": " ".join(str(i.get(x) or "") for x in ("title", "challenge", "approach", "outcome")).strip(),
                      "confidence": i.get("confidence"), "dist": i.get("dist")} for i in items]
        # search_families_semantic devuelve la familia bajo "family_id" (no "id").
        # family_content incluye la razón de la etiqueta humana (el "por qué" del
        # senior) cuando existe — ver auditoría 12-ago, H1.
        # display_title: lo que identifica la familia para quien pregunta. Su `title`
        # es el tipo de error («TimeoutError»); la razón del etiquetador dice qué es.
        families = [{"id": str(f["family_id"]), "type": "defect", "title": f.get("title"),
                     "display_title": f.get("label_reason") or f.get("title"),
                     "content": nl_query.family_content(f), "confidence": "confirmado",
                     "dist": f.get("dist"),
                     "priority": bool(f.get("label_reason") or f.get("has_lesson"))}
                    for f in fams]
        return [_public(s) for s in merge_by_relevance(knowledge, families)]

    def ask(self, *, user_id: str, org_id: str, question: str,
            project: Optional[str] = None) -> Dict[str, Any]:
        sources = self.search_unified(user_id=user_id, org_id=org_id, query=question,
                                      project=project)
        out = nl_query.answer_over_sources(question=question, sources=sources)
        return {**out, "sources": _cited_sources(out.get("citations") or [], sources)}


def _public(source: Dict[str, Any]) -> Dict[str, Any]:
    dist = source.get("dist")
    out = {k: v for k, v in source.items() if k not in _INTERNAL_KEYS}
    return {**out, "score": None if dist is None else round(1.0 - float(dist), 4)}


def _cited_sources(citations: List[str], sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Las fuentes citadas con un título legible, en orden de cita y sin duplicados.
    Solo las que están entre las fuentes recuperadas: un id que el LLM se invente no
    llega a la UI como si fuera una fuente."""
    by_id = {s["id"]: s for s in sources}
    seen, out = set(), []
    for cid in citations:
        src = by_id.get(cid)
        if src is None or cid in seen:
            continue
        seen.add(cid)
        title = src.get("display_title") or src.get("title") or (src.get("content") or "")[:80]
        out.append({"id": cid, "type": src["type"], "title": title})
    return out
