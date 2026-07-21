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
    - tags      = etiqueta de la familia + proyectos afectados (dedup, en orden)
    - domain/outcome = None (editables al aprobar)
    """
    challenge = _join([rca.get("root_cause", ""), rca.get("why_it_happened", "")])
    approach = _join([rca.get("how_to_fix", ""), _numbered(list(rca.get("suggested_fix_steps") or []))])

    tags: List[str] = []
    for t in [family.get("label"), *(projects or [])]:
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
