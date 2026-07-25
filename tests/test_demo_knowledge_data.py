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


def test_hay_tests_indexados_para_que_el_grafo_tenga_cuerpo():
    from src.demo.knowledge_data import TEST_ASSETS
    assert len(TEST_ASSETS) >= 25
    rutas = [a["path"] for a in TEST_ASSETS]
    assert len(rutas) == len(set(rutas)), "dos assets con la misma ruta se pisan al indexar"
    for a in TEST_ASSETS:
        assert a["path"].endswith((".spec.ts", ".test.ts", ".cy.ts", ".spec.py", ".py"))
        assert a["framework"] in ("playwright", "pytest", "cypress")
        assert len(a["content"]) > 80, f"{a['path']} sin cuerpo suficiente para el embedding"


def test_los_tests_indexados_cubren_los_ficheros_donde_ocurren_los_fallos():
    """Grafo y Defect DNA tienen que hablar del mismo código: si una familia de
    defectos apunta a un fichero, ese fichero debe existir en el índice."""
    from src.demo.demo_catalog import FAILURE_CATALOG
    from src.demo.knowledge_data import TEST_ASSETS

    indexados = {a["path"] for a in TEST_ASSETS}
    con_fallo = {f.file for fallos in FAILURE_CATALOG.values() for f in fallos}
    faltan = con_fallo - indexados
    assert not faltan, f"ficheros con fallos que no están indexados: {sorted(faltan)}"


def test_hay_propuestas_pendientes_en_la_bandeja():
    from src.demo.knowledge_data import PROPUESTAS
    assert len(PROPUESTAS) >= 4
    for p in PROPUESTAS:
        assert p.get("title") and p.get("challenge") and p.get("approach") and p.get("outcome")
        assert p["kind"] == "leccion"
        assert p.get("tags")
