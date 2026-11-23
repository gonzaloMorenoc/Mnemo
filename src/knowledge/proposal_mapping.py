"""Mapeo determinista causa-raíz → borrador de lección para la memoria de QA.

Puro (sin BD ni LLM): el objeto estructurado de la causa raíz ya salió del LLM
en el paso previo, así que aquí solo se reorganiza en los campos de qa_knowledge.
`domain` y `outcome` quedan vacíos a propósito (el RCA es una hipótesis previa al
fix, no tiene resultado, y la familia no tiene dominio) → los completa el humano
al aprobar en la bandeja. Retorno inmutable: no muta las entradas.
"""
from typing import Any, Dict, List, Optional, Sequence


def _join(parts: Sequence[str], sep: str = "\n\n") -> str:
    return sep.join(p for p in parts if p)


def _numbered(steps: Sequence[str]) -> str:
    return "\n".join(f"{i}. {s}" for i, s in enumerate((s for s in steps if s), 1))


def rca_to_proposal(family: Dict[str, Any], rca: Dict[str, Any],
                    *, projects: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Construye el borrador de propuesta (kind='leccion') desde una familia y su RCA.

    - challenge = causa raíz + por qué ocurrió
    - approach  = cómo arreglar + pasos sugeridos (numerados)
    - tags      = proyectos afectados (dedup, en orden). La etiqueta de triaje
      (defect_families.label) y la razón humana (triage_corrections.reason) NO se
      copian aquí: ya entran en el prompt de la causa raíz (assurance/root_cause.py),
      así que el RCA del que sale este borrador parte de ellas.
    - domain/outcome = None (editables al aprobar)
    """
    challenge = _join([rca.get("root_cause", ""), rca.get("why_it_happened", "")])
    steps = rca.get("suggested_fix_steps") or []
    if isinstance(steps, str):  # el LLM a veces devuelve un string en vez de lista
        steps = [steps]
    approach = _join([rca.get("how_to_fix", ""), _numbered(list(steps))])

    tags: List[str] = []
    for t in (projects or []):
        if t and t not in tags:
            tags.append(t)

    return {
        "kind": "leccion",
        "title": family.get("title") or "",
        "challenge": challenge or None,
        "approach": approach or None,
        "domain": None,
        "outcome": None,
        "tags": tags,
    }
