import re
from typing import Any, Dict, List, Optional, Sequence

from src.certify.certificate import build_certificate, compute_self_eval
from src.certify.share import share_blob
from src.certify.signing import canonical_json, key_id, sign
from src.ai.judge import compute_ai_eval


_PEM = re.compile(r"-----BEGIN PUBLIC KEY-----.+?-----END PUBLIC KEY-----", re.S)


def parse_public_keys(text: str) -> List[str]:
    """Varias claves públicas PEM pegadas en una sola variable de entorno."""
    return [m.group(0).strip() for m in _PEM.finditer(text or "")]


def _key_id_de(cert: Dict[str, Any]) -> str:
    """El key_id que va DENTRO del acta firmada (release: identity.key_id; traspaso:
    key_id en la raíz)."""
    identidad = cert.get("identity") if isinstance(cert.get("identity"), dict) else {}
    return str(identidad.get("key_id") or cert.get("key_id") or "")


class CertificateService:
    """Genera y recupera Release Assurance Certificates. Determinista; firma Ed25519."""

    def __init__(self, *, repo, cert_repo, private_key: str, public_key: str,
                 mnemo_version: str, model_version: str, llm_provider=None,
                 retired_public_keys: Sequence[str] = ()):
        self.repo = repo               # AssuranceRepository (get_triage_for_run)
        self.cert_repo = cert_repo     # CertificateRepository
        self._private_key = private_key
        self._public_key = public_key
        # Anillo de claves: la actual + las retiradas, indexadas por key_id. Rotar la
        # clave ya no invalida las actas emitidas con la anterior.
        self._keyring = {key_id(k): k for k in [*retired_public_keys, public_key] if k}
        self._mnemo_version = mnemo_version
        self._model_version = model_version
        self._llm_provider = llm_provider

    def generate(self, *, user_id: str, run_id: str, created_at: str,
                 require_admin: bool = False) -> Dict[str, Any]:
        meta = self.cert_repo.get_run_meta(user_id=user_id, run_id=run_id)
        if meta is None:
            raise ValueError("run no encontrado o sin acceso")
        # El endpoint humano exige owner/admin; el webhook auto-emite con require_admin=False.
        if require_admin and not self.cert_repo.is_org_admin(user_id=user_id, org_id=meta["org_id"]):
            raise PermissionError("emitir un acta requiere rol owner/admin")
        verdicts = self.repo.get_triage_for_run(user_id=user_id, run_id=run_id)
        if not verdicts and self.repo.count_failures_for_run(user_id=user_id, run_id=run_id) > 0:
            # Fallos ingeridos pero sin veredictos = run sin triar → no certificar.
            # Sin fallos (run verde) sí se certifica: es el caso central "pasó QA".
            raise ValueError("run con fallos sin triar: ejecuta el triaje antes de certificar")
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
            key_id=key_id(self._public_key), manifest=meta.get("manifest"),
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
                "canonical_json": cert, "signature": signature, "created_at": created_at,
                "share": share_blob(cert, signature)}

    def get(self, *, user_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        cert = self.cert_repo.get_certificate(user_id=user_id, run_id=run_id)
        if cert is None:
            return None
        # Copia nueva (no se muta lo que devuelve el repositorio).
        return {**cert, "share": share_blob(cert["canonical_json"], cert["signature"])}

    def verify_payload(self, *, cert: Dict[str, Any], signature: str) -> bool:
        """Verifica con la clave cuyo key_id declara el acta (la actual o una
        retirada). El key_id va firmado: cambiarlo para elegir otra clave rompe la
        firma. Sin key_id conocido, se prueba la clave actual."""
        from src.certify.signing import verify as _verify
        clave = self._keyring.get(_key_id_de(cert), self._public_key)
        return _verify(canonical_json(cert), signature, clave)
