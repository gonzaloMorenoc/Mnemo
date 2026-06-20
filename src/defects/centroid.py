from typing import List, Optional, Sequence


def update_centroid(centroid: Optional[Sequence[float]], count: int, vec: Sequence[float]) -> List[float]:
    """Media movil incremental: nuevo centroide tras observar `vec` (count = nº previo de miembros)."""
    if centroid is None or count <= 0:
        return list(vec)
    if len(centroid) != len(vec):
        raise ValueError(f"vector length mismatch: {len(centroid)} vs {len(vec)}")
    n = count + 1
    return [(c * count + v) / n for c, v in zip(centroid, vec)]
