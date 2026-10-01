from typing import Any, Dict, List

from src.ai import nl_query
from src.defects.embedder import LocalEmbedder


class KnowledgeService:
    def __init__(self, knowledge_repo, assurance_repo, embedder=None):
        self.knowledge = knowledge_repo
        self.assurance = assurance_repo
        self.embedder = embedder or LocalEmbedder()

    def search_unified(self, *, user_id: str, org_id: str, query: str, k: int = 8) -> List[Dict[str, Any]]:
        emb = self.embedder.embed(query)
        items = self.knowledge.search_semantic(user_id=user_id, org_id=org_id, query_embedding=emb, k=k)
        fams = self.assurance.search_families_semantic(user_id=user_id, org_id=org_id, query_embedding=emb, k=k)
        out = [{"id": str(i["id"]), "type": "knowledge", "title": i.get("title"),
                "content": " ".join(str(i.get(x) or "") for x in ("title", "challenge", "approach", "outcome")).strip(),
                "confidence": i.get("confidence")} for i in items]
        # search_families_semantic devuelve la familia bajo "family_id" (no "id").
        # family_content incluye la razón de la etiqueta humana (el "por qué" del
        # senior) cuando existe — ver auditoría 12-ago, H1.
        # display_title: lo que identifica la familia para quien pregunta. Su `title`
        # es el tipo de error («TimeoutError»); la razón del etiquetador dice qué es.
        out += [{"id": str(f["family_id"]), "type": "defect", "title": f.get("title"),
                 "display_title": f.get("label_reason") or f.get("title"),
                 "content": nl_query.family_content(f), "confidence": "confirmado"} for f in fams]
        return out

    def ask(self, *, user_id: str, org_id: str, question: str) -> Dict[str, Any]:
        sources = self.search_unified(user_id=user_id, org_id=org_id, query=question)
        out = nl_query.answer_over_sources(question=question, sources=sources)
        return {**out, "sources": _cited_sources(out.get("citations") or [], sources)}


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
