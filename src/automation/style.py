from typing import Optional

_MAX_EXAMPLES_CHARS = 6000


def retrieve_style_examples(*, user_id: str, org_id: str, case_text: str,
                            asset_repo, embedder, k: int = 3) -> Optional[str]:
    """Recupera los k test_assets más similares al caso y los concatena como
    ejemplos de estilo (few-shot). Devuelve None si no hay tests indexados.
    Membership-gated vía asset_repo.search_semantic (no-miembro → [] → None)."""
    embedding = list(embedder.embed(case_text or ""))
    rows = asset_repo.search_semantic(
        user_id=user_id, org_id=org_id, query_embedding=embedding, k=k)
    parts = []
    total = 0
    for r in rows or []:
        content = (r.get("content") or "").strip()
        if not content:
            continue
        block = f"// --- ejemplo: {r.get('path') or 'test'} ---\n{content}"
        if total + len(block) > _MAX_EXAMPLES_CHARS:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts) if parts else None
