"""Auditoría 2026-11-23 #13: había 5-6 copias del modelo de embeddings en RAM y en
`/automation/generate` y `/repo/index` se cargaba en cada petición. Un único modelo por
proceso, con carga perezosa thread-safe (lock con doble comprobación)."""
import threading
import time

import src.api_v2 as api_v2
from src.defects import embedder as embedder_mod
from src.defects.embedder import LocalEmbedder, get_shared_embedder

_LOAD_DELAY_SECONDS = 0.05
_THREADS = 8


class _FakeHF:
    instances = 0

    def __init__(self, model_name):
        type(self).instances += 1
        time.sleep(_LOAD_DELAY_SECONDS)   # ventana para que la carrera se note
        self.model_name = model_name

    def embed_query(self, text):
        return [float(len(text))]


def _reset(monkeypatch):
    _FakeHF.instances = 0
    monkeypatch.setattr(embedder_mod, "_models", {})
    monkeypatch.setattr(embedder_mod, "_hf_factory", lambda name: _FakeHF(name))


def test_carga_concurrente_instancia_el_modelo_una_sola_vez(monkeypatch):
    _reset(monkeypatch)
    embedders = [LocalEmbedder() for _ in range(_THREADS)]
    threads = [threading.Thread(target=e.embed, args=("hola",)) for e in embedders]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert _FakeHF.instances == 1


def test_varias_instancias_comparten_el_modelo(monkeypatch):
    _reset(monkeypatch)
    a, b = LocalEmbedder(), LocalEmbedder()
    assert a.embed("ab") == [2.0] and b.embed("abc") == [3.0]
    assert _FakeHF.instances == 1


def test_modelos_distintos_no_se_mezclan(monkeypatch):
    _reset(monkeypatch)
    LocalEmbedder("m1").embed("x")
    LocalEmbedder("m2").embed("x")
    assert _FakeHF.instances == 2


def test_get_shared_embedder_es_singleton():
    assert get_shared_embedder() is get_shared_embedder()


def test_dependencias_distintas_devuelven_el_mismo_embedder(monkeypatch):
    from unittest.mock import MagicMock
    monkeypatch.setattr(api_v2, "multi_tenant_enabled", lambda: True)
    monkeypatch.setattr(api_v2, "get_assurance_repo", lambda: MagicMock())
    monkeypatch.setattr(api_v2, "get_integrations_repo", lambda: MagicMock())
    for name in ("_ingestion_service", "_jira_service", "_ci_ingestion_service",
                 "_knowledge_repo", "_embedder"):
        monkeypatch.setattr(api_v2, name, None)
    shared = api_v2.get_embedder()
    assert shared is get_shared_embedder()
    assert api_v2.get_ingestion_service().embedder is shared
    assert api_v2.get_ci_ingestion_service().embedder is shared
    assert api_v2.get_jira_ingestion_service().embedder is shared
    assert api_v2.get_knowledge_repo().embedder is shared


def test_repositorios_por_peticion_reutilizan_el_embedder():
    from src.knowledge.proposal_repository import KnowledgeProposalRepository
    from src.repo_ingest.repository import TestAssetRepository
    assert TestAssetRepository().embedder is get_shared_embedder()
    assert KnowledgeProposalRepository(db_url="postgresql://x").embedder is get_shared_embedder()
