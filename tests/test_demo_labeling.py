"""La calibración de la demo se gana etiquetando, y tiene que ser creíble."""
from src.demo.labeling import CORRECCION_ALTERNATIVA, etiqueta_humana

_CATEGORIAS = ("real", "flaky", "maintenance", "infra")


def test_la_mayoria_confirma_al_motor_y_una_minoria_corrige():
    decisiones = [etiqueta_humana("flaky", i) for i in range(100)]
    aciertos = sum(1 for d in decisiones if d == "flaky")
    assert 80 <= aciertos <= 90, f"precisión fuera del objetivo: {aciertos}%"


def test_es_determinista():
    assert etiqueta_humana("real", 7) == etiqueta_humana("real", 7)


def test_la_correccion_es_una_categoria_valida_y_distinta():
    correcciones = {etiqueta_humana(c, i) for c in _CATEGORIAS for i in range(20)}
    assert correcciones <= set(_CATEGORIAS)
    for c in _CATEGORIAS:
        alternativa = CORRECCION_ALTERNATIVA[c]
        assert alternativa != c and alternativa in _CATEGORIAS


def test_nunca_devuelve_unknown():
    # Una familia etiquetada 'unknown' es ruido: es justo lo que este seed elimina.
    assert "unknown" not in {etiqueta_humana(c, i) for c in _CATEGORIAS for i in range(50)}


def test_una_categoria_desconocida_del_motor_se_etiqueta_igualmente():
    # El motor puede no clasificar (categoría 'unknown'): el humano SIEMPRE decide.
    assert etiqueta_humana("unknown", 3) in _CATEGORIAS


def test_la_precision_se_mantiene_por_encima_del_umbral_de_confianza_baja():
    # Por debajo de 0.60 el motor vuelve a confianza baja y no habría actas verdes:
    # la precisión sembrada tiene que dejar margen sobre ese suelo.
    for categoria in _CATEGORIAS:
        aciertos = sum(1 for i in range(100) if etiqueta_humana(categoria, i) == categoria)
        assert aciertos / 100 > 0.60


def test_con_pocas_familias_la_precision_sigue_siendo_creible():
    """Una demo real ronda las 35 familias. Con un reparto mal planteado no habría
    ni una corrección en ese rango y la precisión saldría del 100%."""
    for n_familias in (20, 34, 45):
        decisiones = [etiqueta_humana("real", i) for i in range(n_familias)]
        aciertos = sum(1 for d in decisiones if d == "real") / n_familias
        assert 0.70 <= aciertos <= 0.95, (
            f"con {n_familias} familias la precisión sale {aciertos:.0%}")
