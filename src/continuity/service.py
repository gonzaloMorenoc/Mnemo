"""Emisión del acta de traspaso: índice → payload canónico → firma Ed25519.

Reusa la cadena del acta de release SIN tocarla (signing + share): el acta de
traspaso viaja en un enlace y se verifica por la misma puerta pública, que es
agnóstica del payload. Lo único que las distingue es el campo `schema`.

`created_at` llega del endpoint — nada de now() dentro de la lógica firmada, mismo
patrón que el acta de release: lo que se firma tiene que ser reproducible.
"""
from typing import Any, Dict, Optional

from src.certify.share import share_blob
from src.certify.signing import canonical_json, key_id, sign
from src.continuity.index import compute_index, list_projects

SCHEMA = "mnemo.traspaso.v1"


class ContinuityService:
    def __init__(self, *, repo, private_key: str, public_key: str, mnemo_version: str,
                 index_fn=compute_index, projects_fn=list_projects):
        self.repo = repo                 # ContinuityRepository
        self._private_key = private_key
        self._public_key = public_key
        self._mnemo_version = mnemo_version
        self._index_fn = index_fn        # inyectables: los unit tests no tocan la BD
        self._projects_fn = projects_fn

    def emit_handover(self, *, user_id: str, org_id: str, project: str,
                      created_at: str) -> Dict[str, Any]:
        """Emite y firma el acta de traspaso del proyecto.

        PermissionError si no es owner/admin; ValueError si el proyecto no existe
        en la org; SigningKeyMissing si no hay clave de firma configurada.
        """
        if not self.repo.is_org_admin(user_id=user_id, org_id=org_id):
            raise PermissionError("emitir un acta de traspaso requiere rol owner/admin")
        if project not in self._projects_fn(user_id=user_id, org_id=org_id):
            raise ValueError("proyecto no encontrado en esta organización")
        idx = self._index_fn(user_id=user_id, org_id=org_id, project=project)
        # El desglose entero viaja dentro: el acta es RECALCULABLE. Quien tenga los
        # datos puede reproducir el número, y los pesos van con ella para que dos
        # actas emitidas con pesos distintos sigan siendo comparables.
        payload = {
            "schema": SCHEMA,
            "org_id": org_id,
            "project": project,
            "created_at": created_at,
            "emitted_by": user_id,
            "continuity": {"score": idx["score"], "dimensions": idx["dimensions"]},
            "inventario": idx["inventario"],
            "mnemo_version": self._mnemo_version,
            "key_id": key_id(self._public_key),
        }
        signature = sign(canonical_json(payload), self._private_key)
        self.repo.save_act(user_id=user_id, org_id=org_id, project=project,
                           canonical_json=payload, signature=signature,
                           score=idx["score"], created_by=user_id)
        return {"canonical_json": payload, "signature": signature,
                "share": share_blob(payload, signature),
                "score": idx["score"], "created_at": created_at}

    def latest_handover(self, *, user_id: str, org_id: str,
                        project: str) -> Optional[Dict[str, Any]]:
        """La última acta del proyecto con su enlace regenerado, o None."""
        act = self.repo.latest_act(user_id=user_id, org_id=org_id, project=project)
        if act is None:
            return None
        return {**act, "share": share_blob(act["canonical_json"], act["signature"])}
