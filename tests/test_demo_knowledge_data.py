"""Invariantes del dataset de conocimiento de demo (sin BD).

El corpus debe cubrir TODOS los kinds del esquema (018_qa_knowledge.sql) y ser
contenido real (título + narrativa + dominio + tags), no relleno.
"""
from src.demo.knowledge_data import KNOWLEDGE_ORG_A, KNOWLEDGE_ORG_B, TEST_ASSETS

ALL_KINDS = {"regla_negocio", "flujo", "riesgo", "glosario", "leccion", "reto", "patron"}


def test_org_a_covers_all_kinds():
    kinds = {item["kind"] for item in KNOWLEDGE_ORG_A}
    assert kinds == ALL_KINDS, f"faltan kinds: {ALL_KINDS - kinds}"


def test_items_have_substance():
    for item in KNOWLEDGE_ORG_A + KNOWLEDGE_ORG_B:
        assert item["title"].strip(), item
        assert item.get("domain"), f"sin dominio: {item['title']}"
        assert item.get("tags"), f"sin tags: {item['title']}"
        narrativa = (item.get("challenge") or "") + (item.get("approach") or "")
        assert len(narrativa) >= 40, f"narrativa pobre: {item['title']}"


def test_org_b_is_distinct_world():
    titles_a = {i["title"] for i in KNOWLEDGE_ORG_A}
    titles_b = {i["title"] for i in KNOWLEDGE_ORG_B}
    assert titles_b and not (titles_a & titles_b)


def test_assets_have_path_and_content():
    assert len(TEST_ASSETS) >= 3
    for a in TEST_ASSETS:
        assert a["path"].endswith((".spec.ts", ".cy.ts", ".py"))
        assert len(a["content"]) >= 200, f"asset vacío: {a['path']}"
        assert a.get("domain")
