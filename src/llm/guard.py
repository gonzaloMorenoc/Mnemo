"""Guardián del punto de salida a un LLM EXTERNO (auditoría 23-nov, #17 / H5).

Toda llamada a un proveedor externo (OpenAI-compatible, Anthropic) pasa por aquí,
una sola vez y de forma centralizada (lo aplica la factoría):

1. Política por org: si la org fijada para la petición ha desactivado el LLM
   externo, se lanza `ExternalLLMDisabledForOrg`. Los llamantes ya tratan cualquier
   excepción del proveedor como «sin LLM» y degradan a su vía determinista.
2. Saneado: el prompt completo pasa por `sanitize_for_llm` (secretos y datos
   personales) antes de salir. Así se cubre lo que no se saneaba en la ingesta: HU
   pegadas, conocimiento creado a mano, razones de etiqueta, preguntas, issues de
   Jira resueltas…

El proveedor local (Ollama) no se envuelve: los datos no salen de la máquina.
"""
import logging
from typing import Callable

from src.llm.org_policy import (
    ExternalLLMDisabledForOrg,
    current_llm_org,
    external_llm_allowed,
    has_llm_org_scope,
)
from src.llm.provider import LLMProvider
from src.sanitizer import sanitize_for_llm

logger = logging.getLogger(__name__)


class ExternalLLMGuard:
    def __init__(self, inner: LLMProvider, *,
                 policy: Callable[[str], bool] = external_llm_allowed,
                 sanitize: Callable[[str], str] = sanitize_for_llm):
        self.inner = inner
        self._policy = policy
        self._sanitize = sanitize

    def _check_org_policy(self) -> None:
        if not has_llm_org_scope():
            logger.debug("llamada al LLM externo sin org fijada: solo política global")
            return
        try:
            org_id = current_llm_org()
        except Exception as exc:  # noqa: BLE001 — sin saber la org, falla cerrado
            raise ExternalLLMDisabledForOrg(
                "no se pudo determinar la organización de los datos") from exc
        if org_id is not None and not self._policy(org_id):
            raise ExternalLLMDisabledForOrg(
                "la organización ha desactivado el LLM externo")

    def complete(self, prompt: str) -> str:
        self._check_org_policy()
        return self.inner.complete(self._sanitize(prompt))
