from typing import Any, Dict, Optional

from src.certify.certificate import build_certificate, compute_self_eval
from src.certify.signing import canonical_json, sign
from src.ai.judge import compute_ai_eval


class CertificateService:
    """Genera y recupera Release Assurance Certificates. Determinista; firma Ed25519."""

    def __init__(self, *, repo, cert_repo, private_key: str, public_key: str,
                 mnemo_version: str, model_version: str, llm_provider=None):
        self.repo = repo               # AssuranceRepository (get_triage_for_run)
        self.cert_repo = cert_repo     # CertificateRepository
        self._private_key = private_key
        self._public_key = public_key
        self._mnemo_version = mnemo_version
        self._model_version = model_version
        self._llm_provider = llm_provider

    def generate(self, *, user_id: str, run_id: str, created_at: str) -> Dict[str, Any]:
        meta = self.cert_repo.get_run_meta(user_id=user_id, run_id=run_id)
        if meta is None:
            raise ValueError("run no encontrado o sin acceso")
        verdicts = self.repo.get_triage_for_run(user_id=user_id, run_id=run_id)
        if not verdicts:
            raise ValueError("run sin veredictos de triaje")
        raw_cal = self.repo.get_calibration_metrics(user_id=user_id, org_id=meta["org_id"]) or {}
        calibration = {
            "tenant_accuracy": raw_cal.get("accuracy", 0.0),
            "n_corrections": raw_cal.get("total", 0),
            "por_categoria_humana": raw_cal.get("por_categoria", {}),
        }
        try:
            ai_eval = compute_ai_eval(verdicts=verdicts, created_at=created_at,
                                      provider=self._llm_provider, judge_model=self._model_version)
        except Exception:  # noqa: BLE001 — el judge nunca rompe la emisión del certificado
            ai_eval = None
        self_eval = compute_self_eval(calibration=calibration, verdicts=verdicts,
                                      created_at=created_at, ai_eval=ai_eval)
        cert = build_certificate(
            run={"org_id": meta["org_id"], "project": meta["project"],
                 "commit_sha": meta["commit_sha"], "run_id": run_id},
            verdicts=verdicts, sign_offs=[], mnemo_version=self._mnemo_version,
            model_version=self._model_version, created_at=created_at, self_eval=self_eval,
        )
        canonical = canonical_json(cert)
        signature = sign(canonical, self._private_key)  # SigningKeyMissing si falta
        self.cert_repo.save_certificate(
            user_id=user_id, org_id=meta["org_id"], run_id=run_id, canonical_json=cert,
            signature=signature, verdict=cert["verdict"], risk_score=cert["risk_score"],
            sign_offs=cert["sign_offs"], mnemo_version=self._mnemo_version,
            model_version=self._model_version,
        )
        return {"run_id": run_id, "verdict": cert["verdict"], "risk_score": cert["risk_score"],
                "canonical_json": cert, "signature": signature, "created_at": created_at}

    def get(self, *, user_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        return self.cert_repo.get_certificate(user_id=user_id, run_id=run_id)

    def verify_payload(self, *, cert: Dict[str, Any], signature: str) -> bool:
        from src.certify.signing import verify as _verify
        return _verify(canonical_json(cert), signature, self._public_key)
