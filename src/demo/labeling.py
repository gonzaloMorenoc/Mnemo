"""Qué etiqueta pone el humano a una familia, dada la que puso el motor.

La calibración de un tenant es `aciertos/total` sobre las correcciones
(`AssuranceRepository.get_calibration_metrics`), donde un "acierto" es que el
humano confirme la categoría del motor. Etiquetar siempre igual daría un 100%
que nadie se cree —y que significaría que el humano nunca aportó nada—, así que
esta función reparte confirmaciones y correcciones para fijar una precisión
objetivo, de forma determinista para que el re-seed sea reproducible.
"""
from typing import Dict

# A dónde corrige el humano cuando NO está de acuerdo con el motor. Las parejas
# son las confusiones plausibles en QA: un fallo intermitente que en realidad era
# de infraestructura, un selector roto que resultó ser un defecto real.
CORRECCION_ALTERNATIVA: Dict[str, str] = {
    "flaky": "infra",
    "infra": "flaky",
    "maintenance": "real",
    "real": "maintenance",
    "unknown": "real",
}

_FALLBACK = "real"
_PRECISION_OBJETIVO = 0.85


def etiqueta_humana(engine_category: str, indice: int,
                    precision: float = _PRECISION_OBJETIVO) -> str:
    """Etiqueta que pone el humano a la familia `indice`-ésima.

    El motor sin clasificar ('unknown') SIEMPRE se corrige: dejar una familia en
    'unknown' es exactamente el ruido que esta siembra elimina.
    """
    alternativa = CORRECCION_ALTERNATIVA.get(engine_category, _FALLBACK)
    if engine_category not in CORRECCION_ALTERNATIVA or engine_category == "unknown":
        return alternativa
    # Se corrige una de cada `paso` familias, repartidas. Con un umbral del tipo
    # "índice >= 85" no habría ni una corrección hasta la familia 85, y una demo
    # real ronda las 35: la precisión saldría del 100%, que no se lo cree nadie.
    paso = max(2, round(1 / max(1e-9, 1 - precision)))
    corrige = (indice % paso) == paso - 1
    return alternativa if corrige else engine_category
