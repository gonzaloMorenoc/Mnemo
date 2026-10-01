"""La huella del conocimiento depositado en un proyecto: lo que firma el acta.

El acta de traspaso firmaba solo RECUENTOS (índice, dimensiones, inventario): si al
día siguiente se borraba la memoria, el acta seguía diciendo 95. Aquí se calcula una
huella SHA-256 del CONTENIDO —cada lección, runbook, contacto, decisión… y la razón
con la que se etiquetó cada familia—, de modo que cambiar o borrar un solo elemento
la rompe. Va dentro del acta firmada (n + huella, no la lista: el acta viaja en un
enlace de ≤4 KB) y Mnemo la recalcula para decir si lo depositado sigue intacto.

Determinista y sin LLM, como todo lo que se firma.
"""
import hashlib
from typing import Any, Dict, Iterable, List, Optional

from src.certify.signing import canonical_json
from src.db.pool import get_pool

# Campos que forman el contenido de un elemento. id y tipo entran también: mover un
# texto de un elemento a otro, o cambiarle el tipo, es cambiar lo depositado.
_CAMPOS = ("id", "tipo", "title", "challenge", "approach", "outcome")


def item_digest(item: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json({k: item.get(k) for k in _CAMPOS})).hexdigest()


def deposit_digest(items: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Huella global: SHA-256 de las huellas de cada elemento ordenadas por id
    (independiente del orden de lectura) + cuántos hay y de qué tipo."""
    items = list(items)
    lineas = sorted(f"{i['id']}:{item_digest(i)}" for i in items)
    raiz = hashlib.sha256("\n".join(lineas).encode("utf-8")).hexdigest()
    por_tipo: Dict[str, int] = {}
    for i in items:
        por_tipo[i["tipo"]] = por_tipo.get(i["tipo"], 0) + 1
    return {"n": len(items), "sha256": raiz, "por_tipo": dict(sorted(por_tipo.items()))}


# Conocimiento activo del proyecto + la ÚLTIMA razón con la que se etiquetó cada
# familia con fallos en el proyecto (lo que dejó escrito quien etiquetaba).
_Q_CONOCIMIENTO = """
    select id::text as id, kind as tipo, title, challenge, approach, outcome
    from public.qa_knowledge
    where org_id = %(org)s and project = %(proj)s and status = 'activo'
"""

_Q_RAZONES = """
    select distinct on (tc.family_id)
           tc.family_id::text as id, 'razon_etiqueta' as tipo, df.title as title,
           null::text as challenge, tc.reason as approach, tc.human_category as outcome
    from public.triage_corrections tc
    join public.defect_families df on df.id = tc.family_id and df.org_id = tc.org_id
    where tc.org_id = %(org)s
      and coalesce(btrim(tc.reason), '') <> ''
      and exists (select 1 from public.failures fl
                  join public.test_runs tr on tr.id = fl.run_id
                  where fl.defect_family_id = df.id
                    and tr.org_id = %(org)s and tr.project = %(proj)s)
    order by tc.family_id, tc.corrected_at desc
"""


def load_deposit(cur, *, org_id: str, project: str) -> List[Dict[str, Any]]:
    params = {"org": org_id, "proj": project}
    cur.execute(_Q_CONOCIMIENTO, params)
    items = [dict(r) for r in cur.fetchall()]
    cur.execute(_Q_RAZONES, params)
    return items + [dict(r) for r in cur.fetchall()]


def compute_deposit(*, user_id: str, org_id: str, project: str) -> Optional[Dict[str, Any]]:
    """Huella de lo depositado en el proyecto. None si no es miembro: el pooler
    hace BYPASS de RLS, así que la pertenencia se comprueba aquí, como en el resto."""
    with get_pool().connection() as conn, conn.cursor() as cur:
        cur.execute("select exists(select 1 from public.memberships"
                    " where org_id=%s and user_id=%s) as ok", (org_id, user_id))
        if not cur.fetchone()["ok"]:
            return None
        return deposit_digest(load_deposit(cur, org_id=org_id, project=project))
