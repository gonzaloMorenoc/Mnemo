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
        out += [{"id": str(f["id"]), "type": "defect", "title": f.get("title"),
                 "content": f"defecto={f.get('title')} etiqueta={f.get('label')} causa={f.get('root_cause') or 'n/d'}",
                 "confidence": "confirmado"} for f in fams]
        return out

    def ask(self, *, user_id: str, org_id: str, question: str) -> Dict[str, Any]:
        sources = self.search_unified(user_id=user_id, org_id=org_id, query=question)
        return nl_query.answer_over_sources(question=question, sources=sources)
