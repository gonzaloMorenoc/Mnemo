from typing import Any, Dict, List


SCOPE_PRIORITY = ("org", "user", "global")


def prioritize_scoped_results(scoped_results: Dict[str, List[Dict[str, Any]]], max_results: int) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    seen_chunk_ids = set()

    for scope in SCOPE_PRIORITY:
        for row in scoped_results.get(scope, []):
            chunk_id = str(row["chunk_id"])
            if chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)
            results.append(row)
            if len(results) >= max(1, max_results):
                return results
    return results
