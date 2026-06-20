from typing import Any, Dict, List


def build_verdict(*, run_summary: Dict[str, Any], run_families: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Veredicto determinista de un run. La narrativa LLM se anade aparte (Narrator)."""
    known = int(run_summary.get("known", 0))
    novel = int(run_summary.get("novel", 0))
    ingested = int(run_summary.get("ingested", 0))
    ordered = sorted(run_families, key=lambda f: f["occurrence_count"], reverse=True)
    top = [
        {
            "id": str(f["id"]),
            "title": f["title"],
            "occurrence_count": f["occurrence_count"],
            "recurring": f["occurrence_count"] > f["run_count"],
        }
        for f in ordered[:5]
    ]
    return {
        "ingested": ingested,
        "known": known,
        "novel": novel,
        "risk": "atencion" if novel > 0 else "ok",
        "top_families": top,
    }
