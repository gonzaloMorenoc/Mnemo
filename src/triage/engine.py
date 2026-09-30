from dataclasses import dataclass

from src.triage.signals import Signals

_APPROVAL_THRESHOLD = 0.80
_HUMAN_CATEGORIES = ("flaky", "real", "maintenance", "infra")
# Etiquetas humanas que hacen DESAPARECER el fallo del veredicto: solo 'real' y
# 'maintenance' fuerzan "apto-con-reservas" (ver certify/certificate.py), así que
# un prior 'flaky'/'infra' equivocado es el único que puede esconder un defecto.
_SILENCING_LABELS = ("flaky", "infra")


@dataclass
class TriageVerdict:
    category: str          # flaky | infra | maintenance | real | unknown
    confidence: float
    rule_applied: str
    requires_approval: bool
    llm_assisted: bool
    ambiguous: bool


def _prior_contradicho(signals: Signals) -> bool:
    """¿La evidencia de ESTE fallo contradice la etiqueta humana de la familia?

    Un prior es una presunción, no un veredicto. Sin esto, una familia 'flaky'
    devuelve 'flaky' para siempre (con historia, `novel` es False) y un defecto
    real que aparece en un test ya silenciado queda enterrado — y firmado.
    Solo se cuestionan las etiquetas que silencian el fallo, y solo ante una
    aserción que falla SIN rastro de intermitencia ni firma de entorno."""
    if signals.family_label not in _SILENCING_LABELS or not signals.assertion_failure:
        return False
    if signals.retry_passed_in_run or signals.intermittent_same_sha:
        return False
    if signals.family_label == "infra" and (signals.infra_error or signals.mass_cofailure):
        return False
    return True


def triage(signals: Signals) -> TriageVerdict:
    """Clasificación determinista por reglas de prioridad. R0 aplica el prior humano
    calibrado; el ambiguo (R6) queda 'unknown' + ambiguous=True para el desempate LLM."""
    # R0' — el prior silenciador choca con la evidencia: el motor no decide solo.
    # 'unknown' + aprobación obligatoria (no 'real'): `expect(` de Playwright cuenta
    # como aserción incluso en timeouts flaky, así que afirmar 'real' sería ruido.
    # La aprobación pendiente fuerza no-apto hasta que un humano lo revise.
    if _prior_contradicho(signals) and not signals.novel:
        return TriageVerdict(
            category="unknown", confidence=0.5, rule_applied="R0_prior_contradicted",
            requires_approval=True, llm_assisted=False, ambiguous=False,
        )
    # R0 — prior humano calibrado (todas las categorías), salvo señal fuerte de real novedoso
    if signals.family_label in _HUMAN_CATEGORIES and not (signals.assertion_failure and signals.novel):
        return TriageVerdict(
            category=signals.family_label, confidence=0.95, rule_applied="R0_calibrated",
            requires_approval=False, llm_assisted=False, ambiguous=False,
        )
    if signals.retry_passed_in_run or signals.intermittent_same_sha:
        return _verdict("flaky", 0.90, "R1_flaky")
    if signals.mass_cofailure and signals.infra_error:
        return _verdict("infra", 0.90, "R2_infra")
    if (signals.locator_error and not signals.assertion_failure
            and signals.has_green_baseline and signals.dom_changed):
        return _verdict("maintenance", 0.80, "R3_maintenance")
    if signals.assertion_failure and signals.recurrent:
        return _verdict("real", 0.85, "R4_real_recurrent")
    if signals.assertion_failure and signals.novel:
        return _verdict("real", 0.75, "R5_real_novel", novel=True)
    return TriageVerdict(
        category="unknown", confidence=0.0, rule_applied="R6_ambiguous",
        requires_approval=True, llm_assisted=False, ambiguous=True,
    )


def _verdict(category: str, confidence: float, rule: str, *, novel: bool = False) -> TriageVerdict:
    requires_approval = confidence < _APPROVAL_THRESHOLD or (category == "real" and novel)
    return TriageVerdict(
        category=category, confidence=confidence, rule_applied=rule,
        requires_approval=requires_approval, llm_assisted=False, ambiguous=False,
    )
