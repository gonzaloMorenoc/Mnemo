import copy

from src.knowledge.proposal_mapping import rca_to_proposal


def test_maps_rca_to_leccion_fields():
    family = {"id": "fam1", "title": "Timeout en checkout"}
    rca = {
        "root_cause": "El selector cambió.",
        "why_it_happened": "Refactor del DOM sin actualizar el test.",
        "how_to_fix": "Actualizar el locator.",
        "suggested_fix_steps": ["Abrir el spec", "Cambiar el selector"],
        "citations": ["failure:1"],
        "confidence": 0.8,
    }
    p = rca_to_proposal(family, rca, projects=["web", "mobile"])
    assert p["kind"] == "leccion"
    assert p["title"] == "Timeout en checkout"
    # challenge = causa raíz + por qué
    assert "El selector cambió." in p["challenge"]
    assert "Refactor del DOM" in p["challenge"]
    # approach = cómo arreglar + pasos numerados
    assert "Actualizar el locator." in p["approach"]
    assert "1. Abrir el spec" in p["approach"]
    assert "2. Cambiar el selector" in p["approach"]
    # domain/outcome vacíos → los completa el humano al aprobar
    assert p["domain"] is None and p["outcome"] is None
    # tags = proyectos afectados (NO las citations, que son ids; defect_families no tiene label)
    assert p["tags"] == ["web", "mobile"]
    assert "failure:1" not in p["tags"]


def test_suggested_fix_steps_as_string_is_wrapped():
    # el LLM a veces devuelve un string en vez de lista → no debe trocearse en caracteres
    family = {"id": "f", "title": "T"}
    rca = {"root_cause": "c", "how_to_fix": "h", "suggested_fix_steps": "un solo paso"}
    p = rca_to_proposal(family, rca)
    assert "1. un solo paso" in p["approach"]
    assert "1. u\n2. n" not in p["approach"]


def test_omits_empty_pieces_no_dangling_separators():
    family = {"id": "f", "title": "T"}
    rca = {"root_cause": "solo causa", "why_it_happened": "", "how_to_fix": "solo fix",
           "suggested_fix_steps": [], "citations": [], "confidence": 0.0}
    p = rca_to_proposal(family, rca)
    assert p["challenge"] == "solo causa"     # sin "\n\n" colgando
    assert p["approach"] == "solo fix"
    assert p["tags"] == []


def test_all_empty_rca_gives_none_bodies():
    family = {"id": "f", "title": "T"}
    rca = {"root_cause": "", "why_it_happened": "", "how_to_fix": "",
           "suggested_fix_steps": [], "citations": [], "confidence": 0.0}
    p = rca_to_proposal(family, rca)
    assert p["challenge"] is None and p["approach"] is None
    assert p["title"] == "T" and p["kind"] == "leccion"


def test_tags_dedupe_projects():
    family = {"id": "f", "title": "T"}
    rca = {"root_cause": "c", "how_to_fix": "h"}
    p = rca_to_proposal(family, rca, projects=["web", "web", "api"])
    assert p["tags"] == ["web", "api"]         # 'web' no se duplica


def test_does_not_mutate_inputs():
    family = {"id": "f", "title": "T", "label": "d"}
    rca = {"root_cause": "c", "why_it_happened": "w", "how_to_fix": "h",
           "suggested_fix_steps": ["s"], "citations": [], "confidence": 0.5}
    fam_copy, rca_copy = copy.deepcopy(family), copy.deepcopy(rca)
    rca_to_proposal(family, rca, projects=["p"])
    assert family == fam_copy and rca == rca_copy
