"""Regresión de los dos umbrales que dependen del modelo de embeddings (30-sep-2026).

Al pasar al modelo multilingüe (auditoría 12-ago, H2) los umbrales se quedaron con
los valores del modelo inglés. Medidos con el modelo real:

- decide_match (fusión de familias): 0,85 fusionaba 3/10 pares de defectos
  DISTINTOS. Con MATCH_THRESHOLD = 0,90, 1/10 (el de dos URLs, que ningún umbral
  separa) y se siguen fusionando 7/10 pares del MISMO defecto.
- regla_sin_test (cobertura): con el código entero embebido no había umbral que
  separase. Con el descriptor del test y 0,42, las reglas cubiertas encuentran su
  test y las que no tienen ninguno quedan fuera.

Marcado integration: carga el modelo (~470 MB) — el CI lo excluye.
"""
import math

import pytest

from src.defects.embedder import LocalEmbedder
from src.defects.match import MATCH_THRESHOLD
from src.demo.knowledge_data import KNOWLEDGE_ORG_A
from src.demo.riqueza_data import ASSETS, KB_ITEMS
from src.graph.gaps import _COVERAGE_THRESHOLD
from src.knowledge.repository import embedding_text
from src.repo_ingest.descriptor import asset_descriptor
from tests.golden.familias_pares import DISTINTO, MISMO

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def emb():
    return LocalEmbedder()


def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def test_fusion_de_familias_prefiere_no_fusionar(emb):
    mismos = sum(_cos(emb.embed(a), emb.embed(b)) >= MATCH_THRESHOLD for a, b in MISMO)
    distintos = sum(_cos(emb.embed(a), emb.embed(b)) >= MATCH_THRESHOLD for a, b in DISTINTO)
    assert distintos <= 1, f"{distintos}/10 defectos distintos se fusionarían"
    assert mismos >= 7, f"solo {mismos}/10 variaciones del mismo defecto se fusionarían"


def _regla(titulo):
    item = next(i for i in [*KB_ITEMS, *KNOWLEDGE_ORG_A] if i["title"].startswith(titulo))
    return embedding_text(item["title"], item.get("challenge"), item.get("approach"))


# (regla, test que la cubre) — etiquetado a mano sobre los datos de la demo.
_CUBIERTAS = [
    ("Un cupón se aplica una sola vez", "tests/tienda/cupones.spec.ts"),
    ("Un reembolso nunca supera el importe", "tests/api-pagos/reembolsos.test.ts"),
    ("El stock se reserva 15 minutos", "tests/tienda/checkout.spec.ts"),
]
_SIN_TEST = [
    "La pasarela de pagos sandbox limita a 30",
    "Los precios se muestran con IVA",
    "Staging comparte base de datos",
]


@pytest.fixture(scope="module")
def tests_indexados(emb):
    return {a["path"]: emb.embed(asset_descriptor(a["path"], a["content"])) for a in ASSETS}


def test_regla_cubierta_queda_dentro_del_corte_de_su_test(emb, tests_indexados):
    # El hueco regla_sin_test solo decide SI hay un test cerca (no cuál): basta con
    # que el test que de verdad la cubre pase el corte. (El más cercano puede ser
    # otro: «un reembolso nunca supera…» queda a 0,28 de cupones.spec, que también
    # habla de cobros reintentados, y a 0,33 de reembolsos.test.)
    for titulo, path in _CUBIERTAS:
        dist = 1 - _cos(emb.embed(_regla(titulo)), tests_indexados[path])
        assert dist < _COVERAGE_THRESHOLD, f"{titulo!r} a {dist:.3f} de {path}"


def test_regla_sin_test_no_cuenta_como_cubierta(emb, tests_indexados):
    for titulo in _SIN_TEST:
        q = emb.embed(_regla(titulo))
        mejor = min(1 - _cos(q, v) for v in tests_indexados.values())
        assert mejor >= _COVERAGE_THRESHOLD, f"{titulo!r} cubierta por error ({mejor:.3f})"
