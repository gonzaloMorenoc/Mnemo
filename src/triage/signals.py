from dataclasses import dataclass
from typing import Optional

from src.triage.patterns import classify_error


@dataclass
class FailureInput:
    """Entradas ya recuperadas para clasificar un fallo. Los hechos de BD
    (intermitencia, DOM cambiado, etc.) los provee la capa de repositorio (F2d);
    aquí la lógica es PURA."""
    error_type: Optional[str]
    message: str
    is_novel: bool                  # la familia no tiene fallos en runs ANTERIORES (primera vez que se ve)
    family_label: str               # 'flaky'|'real'|'maintenance'|'infra'|'unknown'
    retry_passed_in_run: bool       # pasó al reintentar en el MISMO run
    intermittent_same_sha: bool     # mismo test+commit con mezcla pass+fail entre runs
    mass_cofailure: bool            # el run tiene >= umbral de fallos con firma de infra
    has_green_baseline: bool        # existe snapshot last_green del test
    dom_changed: bool               # DOM de fallo != last_green (normalizado)
    trace: Optional[str] = None     # Playwright call log / stack trace completo


@dataclass
class Signals:
    infra_error: bool
    locator_error: bool
    assertion_failure: bool
    retry_passed_in_run: bool
    intermittent_same_sha: bool
    known_flaky_family: bool
    mass_cofailure: bool
    has_green_baseline: bool
    dom_changed: bool
    novel: bool
    recurrent: bool


def compute_signals(failure: FailureInput) -> Signals:
    cats = classify_error(failure.error_type, failure.message, failure.trace)
    return Signals(
        infra_error="infra" in cats,
        locator_error="locator" in cats,
        assertion_failure="assertion" in cats,
        retry_passed_in_run=failure.retry_passed_in_run,
        intermittent_same_sha=failure.intermittent_same_sha,
        known_flaky_family=failure.family_label == "flaky",
        mass_cofailure=failure.mass_cofailure,
        has_green_baseline=failure.has_green_baseline,
        dom_changed=failure.dom_changed,
        novel=failure.is_novel,
        recurrent=not failure.is_novel,
    )
