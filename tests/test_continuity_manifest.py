"""La huella del conocimiento depositado: lo que el acta de traspaso firma.

Antes el acta firmaba RECUENTOS (índice, dimensiones): si mañana se borraba la
memoria, el acta seguía diciendo 95. Ahora firma una huella del CONTENIDO: si un
solo elemento cambia o desaparece, la huella no cuadra."""
from src.continuity.manifest import deposit_digest, item_digest

ITEM = {"id": "k1", "tipo": "runbook", "title": "Levantar el entorno",
        "challenge": "Sin el simulador todo falla", "approach": "make psp-sim", "outcome": None}


def test_la_huella_de_un_elemento_depende_de_su_contenido():
    assert item_digest(ITEM) == item_digest(dict(ITEM))
    assert item_digest(ITEM) != item_digest({**ITEM, "approach": "make psp-sim --rapido"})


def test_la_huella_global_no_depende_del_orden():
    a = {**ITEM, "id": "a"}
    b = {**ITEM, "id": "b", "title": "Otro"}
    assert deposit_digest([a, b]) == deposit_digest([b, a])


def test_borrar_o_cambiar_un_elemento_cambia_la_huella_global():
    a = {**ITEM, "id": "a"}
    b = {**ITEM, "id": "b", "title": "Otro"}
    base = deposit_digest([a, b])
    assert deposit_digest([a])["sha256"] != base["sha256"]
    assert deposit_digest([a, {**b, "title": "Otro (editado)"}])["sha256"] != base["sha256"]


def test_la_huella_resume_cuantos_elementos_y_de_que_tipo():
    d = deposit_digest([{**ITEM, "id": "a"}, {**ITEM, "id": "b", "tipo": "razon_etiqueta"}])
    assert d["n"] == 2
    assert d["por_tipo"] == {"razon_etiqueta": 1, "runbook": 1}
    assert len(d["sha256"]) == 64


def test_sin_elementos_la_huella_es_estable_y_dice_cero():
    assert deposit_digest([]) == deposit_digest([])
    assert deposit_digest([])["n"] == 0
