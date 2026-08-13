"""El índice de continuidad: ¿cuánto de este proyecto sabe Mnemo?

Determinista y 100% SQL — el mismo principio que el acta de release: determinismo
donde firmo. El LLM no participa en nada que acabe dentro del payload firmado.

Los pesos son opinables y recalibrables (viven aquí, no en una migración) y viajan
DENTRO del acta: dos actas con pesos distintos siguen siendo comparables porque
cada una lleva los suyos.
"""
from typing import Any, Dict, List, Optional

from src.db.pool import get_pool

# Por qué estos pesos: la memoria de defectos es el foso —lo que una wiki no sabe—
# así que se lleva el mayor; la razón de las etiquetas y el oficio son el saber
# tácito y el operativo, equiparables entre sí; reglas_respaldadas depende de que
# haya dominios documentados, más indirecto, y se lleva el menor.
WEIGHTS = {"memoria_defectos": 0.35, "razon_etiquetas": 0.25,
           "oficio": 0.25, "reglas_respaldadas": 0.15}

LABELS = {"memoria_defectos": "Memoria de defectos",
          "razon_etiquetas": "El porqué de las etiquetas",
          "oficio": "Oficio del proyecto",
          "reglas_respaldadas": "Reglas con respaldo"}

OFICIO_KINDS = ("runbook", "dato_prueba", "contacto", "decision")

# Valor por defecto de defect_families.label: la familia existe pero nadie la ha
# triado todavía. No cuenta como etiqueta humana.
UNLABELED = "unknown"

# Familias del proyecto: las que tienen ≥1 fallo en runs de ese proyecto. Una
# familia puede pertenecer a varios proyectos y cuenta en todos.
_Q_FAMILIAS = """
    select df.id, df.label, df.occurrence_count,
           exists (select 1 from public.qa_knowledge k
                   where k.defect_family_id = df.id and k.status = 'activo') as con_conocimiento,
           exists (select 1 from public.triage_corrections tc
                   where tc.family_id = df.id
                     and tc.reason is not null and tc.reason <> '') as con_razon
    from public.defect_families df
    where df.scope = 'org' and df.org_id = %(org)s
      and exists (select 1 from public.failures fl
                  join public.test_runs tr on tr.id = fl.run_id
                  where fl.defect_family_id = df.id
                    and tr.org_id = %(org)s and tr.project = %(proj)s)
"""

_Q_KINDS = """
    select kind, count(*) as n from public.qa_knowledge
    where org_id = %(org)s and project = %(proj)s and status = 'activo'
    group by kind
"""

# El respaldo es del MISMO proyecto: el índice mide lo que el proyecto tiene
# documentado, así que una lección genérica de la org no lo cubre (coherente con
# excluir project IS NULL). Un item sin domain cuenta en el denominador y no puede
# estar respaldado — documentar el dominio es parte de la continuidad.
_Q_REGLAS = """
    select count(*) as den,
           count(*) filter (where k.domain is not null and exists (
               select 1 from public.qa_knowledge l
               where l.org_id = %(org)s and l.project = %(proj)s
                 and l.status = 'activo' and l.domain = k.domain
                 and l.kind in ('leccion','patron'))) as num
    from public.qa_knowledge k
    where k.org_id = %(org)s and k.project = %(proj)s and k.status = 'activo'
      and k.kind in ('regla_negocio','riesgo')
"""

_Q_DOMINIOS = """
    select count(distinct domain) as n from public.qa_knowledge
    where org_id = %(org)s and project = %(proj)s and status = 'activo'
      and domain is not null
"""

_Q_PROJECTS = """
    select distinct project from (
        select tr.project from public.test_runs tr
        where tr.org_id = %(org)s and tr.project is not null
        union
        select k.project from public.qa_knowledge k
        where k.org_id = %(org)s and k.project is not null
    ) p order by 1
"""


def _dim(key: str, num: int, den: int) -> Dict[str, Any]:
    ratio = round(num / den, 4) if den else None
    return {"key": key, "label": LABELS[key], "num": num, "den": den,
            "ratio": ratio, "weight": WEIGHTS[key]}


def _aggregate(dimensions: List[Dict[str, Any]]) -> Optional[int]:
    """Media ponderada sobre las dimensiones CON denominador; sin ninguna → None
    («sin datos suficientes»), nunca un 0 ni un 100 inventados."""
    usables = [d for d in dimensions if d["den"] > 0]
    total = sum(d["weight"] for d in usables)
    if total == 0:
        return None
    return round(100 * sum(d["weight"] * d["ratio"] for d in usables) / total)


def _is_member(cur, org_id: str, user_id: str) -> bool:
    cur.execute("select exists(select 1 from public.memberships"
                " where org_id=%s and user_id=%s) as ok", (org_id, user_id))
    return bool(cur.fetchone()["ok"])


def list_projects(*, user_id: str, org_id: str) -> List[str]:
    """Proyectos con runs o con conocimiento. [] si no es miembro."""
    with get_pool().connection() as conn, conn.cursor() as cur:
        if not _is_member(cur, org_id, user_id):
            return []
        cur.execute(_Q_PROJECTS, {"org": org_id})
        return [r["project"] for r in cur.fetchall()]


def compute_index(*, user_id: str, org_id: str, project: str) -> Optional[Dict[str, Any]]:
    """Índice de continuidad del proyecto. None si el usuario no es miembro.

    Solo lecturas: llamarlo no cambia nada, y el mismo estado da siempre el mismo
    número (por eso puede ir dentro de un acta firmada)."""
    from src.knowledge.repository import KINDS  # import local: evita un ciclo

    params = {"org": org_id, "proj": project}
    with get_pool().connection() as conn, conn.cursor() as cur:
        if not _is_member(cur, org_id, user_id):
            return None
        cur.execute(_Q_FAMILIAS, params)
        fams = cur.fetchall()
        cur.execute(_Q_KINDS, params)
        por_kind = {r["kind"]: r["n"] for r in cur.fetchall()}
        cur.execute(_Q_REGLAS, params)
        reglas = cur.fetchone()
        cur.execute(_Q_DOMINIOS, params)
        dominios = cur.fetchone()["n"]

    recurrentes = [f for f in fams if f["occurrence_count"] >= 2]
    # "Etiquetada" = alguien la miró y decidió. label es NOT NULL con default
    # 'unknown', así que el default NO es una etiqueta humana: contarlo como tal
    # metería en el denominador familias que nadie ha triado y hundiría el índice
    # por algo que no es un fallo de documentación.
    etiquetadas = [f for f in fams if f["label"] != UNLABELED]
    dimensions = [
        _dim("memoria_defectos",
             sum(1 for f in recurrentes if f["con_conocimiento"]), len(recurrentes)),
        _dim("razon_etiquetas",
             sum(1 for f in etiquetadas if f["con_razon"]), len(etiquetadas)),
        _dim("oficio",
             sum(1 for k in OFICIO_KINDS if por_kind.get(k, 0) > 0), len(OFICIO_KINDS)),
        _dim("reglas_respaldadas", reglas["num"], reglas["den"]),
    ]
    return {
        "score": _aggregate(dimensions),
        "dimensions": dimensions,
        "inventario": {
            "familias": len(fams),
            "familias_con_leccion": sum(1 for f in fams if f["con_conocimiento"]),
            "conocimiento_por_kind": {k: por_kind.get(k, 0) for k in sorted(KINDS)},
            "dominios": dominios,
            "etiquetas": len(etiquetadas),
            "etiquetas_con_razon": sum(1 for f in etiquetadas if f["con_razon"]),
        },
    }
