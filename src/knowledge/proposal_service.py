"""Servicio de propuestas de conocimiento — "IA propone / humano aprueba".

Genera borradores de lección desde el análisis de causa raíz de las familias de
defecto sin conocimiento (huecos `defecto_sin_conocimiento`). El humano los aprueba
(entran en qa_knowledge) o los descarta. Nada entra en la memoria sin aprobación.
"""
import logging
from typing import Any, Dict, List, Optional, Sequence

from src.knowledge.proposal_mapping import rca_to_proposal

logger = logging.getLogger(__name__)

_DEFAULT_CAP = 5  # familias por petición: acota el nº de llamadas LLM (analyze_structured)


class KnowledgeProposalService:
    def __init__(self, *, repo, assurance_repo, analyzer):
        self.repo = repo                    # KnowledgeProposalRepository
        self.assurance_repo = assurance_repo  # get_family_with_failures
        self.analyzer = analyzer            # RootCauseAnalyzer

    def generate(self, *, user_id: str, org_id: str,
                 family_ids: Optional[Sequence[str]] = None,
                 cap: int = _DEFAULT_CAP) -> Dict[str, int]:
        """Genera propuestas para hasta `cap` familias sin lección (org-scoped).

        Cada familia = una llamada LLM (analyze_structured); el fallo de una NO aborta
        el lote (error por ítem). Devuelve created/failed y `remaining` (familias que
        siguen sin lección ni propuesta)."""
        candidates = self.repo.candidate_families(
            user_id=user_id, org_id=org_id, limit=cap, family_ids=family_ids)
        created = 0
        failed = 0
        for fam in candidates:
            try:
                ctx = self.assurance_repo.get_family_with_failures(
                    user_id=user_id, defect_id=fam["id"]) or {}
                family = ctx.get("family") or {"id": fam["id"], "title": fam.get("title")}
                failures = ctx.get("failures") or []
                rca = self.analyzer.analyze_structured(family, failures)
                # El LLM cayó → RCA de fallback (confidence 0, sin citas): NO crear una
                # propuesta basura. Al no dejar fila, la familia sigue candidata y se
                # reintenta cuando el LLM vuelva (evita "vacunarla" para siempre).
                if rca.get("confidence", 0.0) == 0.0 and not rca.get("citations"):
                    failed += 1
                    continue
                projects = sorted({f.get("project") for f in failures if f.get("project")})
                fields = rca_to_proposal(family, rca, projects=projects)
                row = self.repo.upsert_proposal(
                    user_id=user_id, org_id=org_id, defect_family_id=fam["id"],
                    run_id=fam.get("run_id"), created_by=user_id, **fields)
                if row:
                    created += 1
                else:
                    failed += 1  # no-op (aprobada/rechazada por carrera) o no-miembro
            except Exception:  # noqa: BLE001 — un fallo por familia no aborta el lote
                logger.exception("generate: falló la propuesta de la familia %s", fam.get("id"))
                failed += 1
        try:
            remaining = self.repo.count_candidate_families(user_id=user_id, org_id=org_id)
        except Exception:  # noqa: BLE001 — las propuestas ya se crearon (commit por familia);
            # un fallo del conteo NO debe ocultar created/failed con un 502.
            logger.exception("generate: no se pudo contar las familias restantes")
            remaining = 0
        return {"created": created, "failed": failed, "remaining": remaining}

    def propose_from_rca(self, *, user_id: str, family: Dict[str, Any],
                         failures: List[Dict[str, Any]], rca: Dict[str, Any]) -> bool:
        """Hook tras el análisis de causa raíz: reusa el RCA YA calculado (cero
        llamadas LLM extra) para dejar una propuesta en la bandeja — solo si la
        familia sigue siendo candidata (sin lección activa y sin propuesta previa;
        no resucita rechazadas). Cierra el lazo: analizar una causa raíz alimenta
        la memoria sin pasos manuales."""
        org_id = family.get("org_id")
        fid = family.get("id")
        if not org_id or not fid:
            return False  # familias globales (org_id None) quedan fuera del MVP
        if rca.get("confidence", 0.0) == 0.0 and not rca.get("citations"):
            return False  # fallback del LLM → no proponer basura
        cands = self.repo.candidate_families(user_id=user_id, org_id=org_id,
                                             limit=1, family_ids=[fid])
        if not cands:
            return False
        projects = sorted({f.get("project") for f in failures if f.get("project")})
        fields = rca_to_proposal(family, rca, projects=projects)
        row = self.repo.upsert_proposal(
            user_id=user_id, org_id=org_id, defect_family_id=fid,
            run_id=cands[0].get("run_id"), created_by=user_id, **fields)
        return bool(row)

    def list(self, *, user_id: str, org_id: str,
             status: str = "pending") -> List[Dict[str, Any]]:
        return self.repo.list_proposals(user_id=user_id, org_id=org_id, status=status)

    def approve(self, *, user_id: str, proposal_id: str, kind: str, title: str,
                challenge: Optional[str], approach: Optional[str], domain: Optional[str],
                outcome: Optional[str], tags: Sequence[str]) -> Optional[Dict[str, Any]]:
        return self.repo.approve(
            user_id=user_id, proposal_id=proposal_id, kind=kind, title=title,
            challenge=challenge, approach=approach, domain=domain, outcome=outcome, tags=tags)

    def reject(self, *, user_id: str, proposal_id: str, reason: str = "") -> bool:
        return self.repo.reject(user_id=user_id, proposal_id=proposal_id, reason=reason)
