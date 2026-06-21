# Capa LLM intercambiable + Análisis de causa raíz — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una capa `LLMProvider` intercambiable (Ollama local / OpenAI-compatible / Anthropic, configurable por entorno) + un análisis de causa raíz por familia de defecto bajo demanda, cacheado, que el LLM configurado genera.

**Architecture:** `src/llm/` aísla el proveedor detrás de `LLMProvider.complete(prompt)->str`; un factory lo elige por env. Consumidores (Narrator migrado, RootCauseAnalyzer nuevo) son agnósticos al proveedor. El análisis se cachea en `defect_families.root_cause`.

**Tech Stack:** Python 3.13, `langchain_ollama` (ya instalado), SDKs `openai` y `anthropic` (nuevos, imports lazy), FastAPI, Postgres; Next.js (un botón + render).

**Referencia de patrón:** `src/assurance/narrator.py` (LLM lazy + degradación), `src/defects/repository.py` (`get_lineage`, membership), `src/api_v2.py` (deps lazy + mapeo de errores).

---

### Task 1: Config + dependencias

**Files:**
- Modify: `src/config.py`
- Modify: `requirements.txt`
- Test: `tests/test_llm_config.py`

- [ ] **Step 1: Write the failing test** — `tests/test_llm_config.py`:

```python
import importlib


def test_llm_config_defaults(monkeypatch):
    for k in ("LLM_PROVIDER", "LLM_MODEL", "OPENAI_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    import src.config as config
    importlib.reload(config)
    assert config.LLM_PROVIDER == "ollama"
    assert config.LLM_MODEL == "deepseek-r1:8b"
    assert config.OPENAI_API_KEY == ""
    assert config.ANTHROPIC_API_KEY == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_llm_config.py -v`
Expected: FAIL with `AttributeError: module 'src.config' has no attribute 'LLM_PROVIDER'`

- [ ] **Step 3: Add config** — in `src/config.py`, after the `MODEL_NAME`/`OLLAMA_BASE_URL` block, add:

```python
# LLM provider intercambiable (ollama local | openai-compatible | anthropic)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", MODEL_NAME)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
```

Then append to `requirements.txt`:
```
openai==1.59.6
anthropic==0.42.0
```

- [ ] **Step 4: Install deps + run test**

Run: `python3 -m pip install 'openai==1.59.6' 'anthropic==0.42.0' && python3 -m pytest tests/test_llm_config.py -v`
Expected: PASS (1 passed). If those exact versions conflict with the installed stack, use the latest compatible `openai`/`anthropic` and pin those instead — report the versions used.

- [ ] **Step 5: Commit**

```bash
git add src/config.py requirements.txt tests/test_llm_config.py
git commit -m "feat: config de proveedor LLM (env) + deps openai/anthropic"
```

---

### Task 2: `strip_reasoning`

**Files:**
- Create: `src/llm/__init__.py` (empty)
- Create: `src/llm/reasoning.py`
- Test: `tests/test_strip_reasoning.py`

- [ ] **Step 1: Write the failing test** — `tests/test_strip_reasoning.py`:

```python
from src.llm.reasoning import strip_reasoning


def test_strips_think_block():
    assert strip_reasoning("<think>razonando...</think>\nLa respuesta") == "La respuesta"


def test_strips_multiline_think():
    assert strip_reasoning("<think>\nlinea1\nlinea2\n</think>respuesta") == "respuesta"


def test_noop_without_think():
    assert strip_reasoning("solo respuesta") == "solo respuesta"


def test_empty():
    assert strip_reasoning("") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_strip_reasoning.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.llm'`

- [ ] **Step 3: Create `src/llm/__init__.py` (empty) and `src/llm/reasoning.py`:**

```python
import re

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Elimina bloques <think>...</think> (modelos de razonamiento) del texto."""
    if not text:
        return text
    return _THINK_RE.sub("", text).strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_strip_reasoning.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/llm/__init__.py src/llm/reasoning.py tests/test_strip_reasoning.py
git commit -m "feat: strip_reasoning (limpia bloques think de LLMs de razonamiento)"
```

---

### Task 3: `LLMProvider` interface

**Files:**
- Create: `src/llm/provider.py`
- Test: `tests/test_llm_provider.py`

- [ ] **Step 1: Write the failing test** — `tests/test_llm_provider.py`:

```python
from src.llm.provider import LLMProvider


class _Fake:
    def complete(self, prompt: str) -> str:
        return "ok"


def test_fake_satisfies_protocol():
    assert isinstance(_Fake(), LLMProvider)


def test_non_provider_rejected():
    assert not isinstance(object(), LLMProvider)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_llm_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.llm.provider'`

- [ ] **Step 3: Write `src/llm/provider.py`:**

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_llm_provider.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/llm/provider.py tests/test_llm_provider.py
git commit -m "feat: interfaz LLMProvider"
```

---

### Task 4: Proveedores (Ollama, OpenAI, Anthropic)

**Files:**
- Create: `src/llm/providers/__init__.py` (empty)
- Create: `src/llm/providers/ollama.py`, `src/llm/providers/openai.py`, `src/llm/providers/anthropic.py`
- Test: `tests/test_llm_providers.py`

- [ ] **Step 1: Write the failing test** — `tests/test_llm_providers.py`:

```python
from src.llm.providers.ollama import OllamaProvider
from src.llm.providers.openai import OpenAIProvider
from src.llm.providers.anthropic import AnthropicProvider


def test_ollama_complete_uses_invoke():
    p = OllamaProvider(model="m", base_url="http://x")
    p._llm = type("L", (), {"invoke": staticmethod(lambda prompt: "respuesta ollama")})()
    assert p.complete("hola") == "respuesta ollama"


def test_openai_complete_extracts_content():
    p = OpenAIProvider(model="gpt", api_key="k")
    class _Resp:
        choices = [type("C", (), {"message": type("M", (), {"content": "respuesta openai"})()})()]
    p._client = type("Cli", (), {"chat": type("Ch", (), {"completions": type("Co", (), {
        "create": staticmethod(lambda **kw: _Resp())})()})()})()
    assert p.complete("hola") == "respuesta openai"


def test_anthropic_complete_joins_text_blocks():
    p = AnthropicProvider(model="claude", api_key="k")
    class _Block:
        type = "text"
        text = "respuesta anthropic"
    class _Resp:
        content = [_Block()]
    p._client = type("Cli", (), {"messages": type("M", (), {
        "create": staticmethod(lambda **kw: _Resp())})()})()
    assert p.complete("hola") == "respuesta anthropic"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_llm_providers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.llm.providers'`

- [ ] **Step 3: Write the three providers.**

`src/llm/providers/__init__.py`: empty.

`src/llm/providers/ollama.py`:
```python
class OllamaProvider:
    """LLM local vía Ollama (langchain_ollama). Carga perezosa."""

    def __init__(self, model: str, base_url: str):
        self._model = model
        self._base_url = base_url
        self._llm = None

    def complete(self, prompt: str) -> str:
        if self._llm is None:
            from langchain_ollama import OllamaLLM
            self._llm = OllamaLLM(model=self._model, base_url=self._base_url)
        return self._llm.invoke(prompt)
```

`src/llm/providers/openai.py`:
```python
from typing import Optional


class OpenAIProvider:
    """LLM vía API compatible OpenAI (OpenAI, Azure, Groq, vLLM...). Carga perezosa."""

    def __init__(self, model: str, api_key: str, base_url: Optional[str] = None):
        self._model = model
        self._api_key = api_key
        self._base_url = base_url or None
        self._client = None

    def complete(self, prompt: str) -> str:
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""
```

`src/llm/providers/anthropic.py`:
```python
class AnthropicProvider:
    """LLM vía API de Anthropic. Carga perezosa."""

    def __init__(self, model: str, api_key: str):
        self._model = model
        self._api_key = api_key
        self._client = None

    def complete(self, prompt: str) -> str:
        if self._client is None:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self._api_key)
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_llm_providers.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/llm/providers tests/test_llm_providers.py
git commit -m "feat: proveedores LLM Ollama, OpenAI-compatible y Anthropic"
```

---

### Task 5: Factory `get_llm_provider`

**Files:**
- Create: `src/llm/factory.py`
- Test: `tests/test_llm_factory.py`

- [ ] **Step 1: Write the failing test** — `tests/test_llm_factory.py`:

```python
import pytest

from src import config
from src.llm.factory import get_llm_provider
from src.llm.providers.ollama import OllamaProvider
from src.llm.providers.openai import OpenAIProvider
from src.llm.providers.anthropic import AnthropicProvider


def test_default_ollama(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    assert isinstance(get_llm_provider(), OllamaProvider)


def test_openai(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "k")
    assert isinstance(get_llm_provider(), OpenAIProvider)


def test_anthropic(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "k")
    assert isinstance(get_llm_provider(), AnthropicProvider)


def test_openai_without_key_raises(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    with pytest.raises(RuntimeError):
        get_llm_provider()


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "foobar")
    with pytest.raises(ValueError):
        get_llm_provider()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_llm_factory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.llm.factory'`

- [ ] **Step 3: Write `src/llm/factory.py`:**

```python
from src import config
from src.llm.provider import LLMProvider
from src.llm.providers.anthropic import AnthropicProvider
from src.llm.providers.ollama import OllamaProvider
from src.llm.providers.openai import OpenAIProvider


def get_llm_provider() -> LLMProvider:
    """Construye el proveedor LLM segun la config de entorno (lazy clients)."""
    provider = (config.LLM_PROVIDER or "ollama").lower()
    if provider == "ollama":
        return OllamaProvider(model=config.LLM_MODEL, base_url=config.OLLAMA_BASE_URL)
    if provider == "openai":
        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY requerida para LLM_PROVIDER=openai")
        return OpenAIProvider(model=config.LLM_MODEL, api_key=config.OPENAI_API_KEY,
                              base_url=config.OPENAI_BASE_URL or None)
    if provider == "anthropic":
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY requerida para LLM_PROVIDER=anthropic")
        return AnthropicProvider(model=config.LLM_MODEL, api_key=config.ANTHROPIC_API_KEY)
    raise ValueError(f"LLM_PROVIDER desconocido: {config.LLM_PROVIDER}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_llm_factory.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/llm/factory.py tests/test_llm_factory.py
git commit -m "feat: factory get_llm_provider (selección por entorno)"
```

---

### Task 6: Migrar el Narrator a `LLMProvider`

**Files:**
- Modify: `src/assurance/narrator.py`
- Modify: `src/api_v2.py` (`get_narrator`)
- Test: `tests/test_narrator.py` (replace its contents)

The current `narrator.py` has `Narrator` (Protocol) + `LocalNarrator` (instantiates `OllamaLLM` directly). We replace `LocalNarrator` with `LLMNarrator(provider)`.

- [ ] **Step 1: Replace the test** — overwrite `tests/test_narrator.py`:

```python
from src.assurance.narrator import LLMNarrator, Narrator


class _FakeProvider:
    def __init__(self, out):
        self.out = out
        self.prompt = None

    def complete(self, prompt: str) -> str:
        self.prompt = prompt
        return self.out


def test_llmnarrator_is_narrator():
    assert isinstance(LLMNarrator(_FakeProvider("x")), Narrator)


def test_summarize_uses_provider_and_strips_think():
    p = _FakeProvider("<think>...</think>Run estable, 0 nuevos.")
    n = LLMNarrator(p)
    out = n.summarize({"known": 3, "novel": 0, "risk": "ok", "top_families": []})
    assert out == "Run estable, 0 nuevos."
    assert "3 fallos conocidos" in p.prompt and "0 nuevos" in p.prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_narrator.py -v`
Expected: FAIL with `ImportError: cannot import name 'LLMNarrator'`

- [ ] **Step 3: Rewrite `src/assurance/narrator.py`:**

```python
from typing import Any, Dict, Protocol, runtime_checkable

from src.llm.provider import LLMProvider
from src.llm.reasoning import strip_reasoning


@runtime_checkable
class Narrator(Protocol):
    def summarize(self, verdict: Dict[str, Any]) -> str: ...


class LLMNarrator:
    """Narrativa del veredicto vía un LLMProvider intercambiable."""

    def __init__(self, provider: LLMProvider):
        self._provider = provider

    def summarize(self, verdict: Dict[str, Any]) -> str:
        recurring = [f["title"] for f in verdict.get("top_families", []) if f.get("recurring")]
        prompt = (
            "Eres un asistente de aseguramiento de calidad. Resume en 2-3 frases el resultado de un run de tests. "
            f"Datos: {verdict.get('known', 0)} fallos conocidos, {verdict.get('novel', 0)} nuevos, "
            f"riesgo='{verdict.get('risk', 'ok')}'. Familias recurrentes: {recurring or 'ninguna'}."
        )
        return strip_reasoning(self._provider.complete(prompt))
```

- [ ] **Step 4: Update the wiring in `src/api_v2.py`.**

Change the import of `LocalNarrator` to `LLMNarrator` (the import line currently reads `from src.assurance.narrator import LocalNarrator, Narrator` — change `LocalNarrator` to `LLMNarrator`). Then update `get_narrator`:

```python
def get_narrator() -> Narrator:
    global _narrator
    if _narrator is None:
        from src.llm.factory import get_llm_provider
        _narrator = LLMNarrator(get_llm_provider())
    return _narrator
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_narrator.py tests/test_api_v2_assurance.py -v`
Expected: PASS. Then `python3 -c "import src.api_v2"` → exit 0.

- [ ] **Step 6: Commit**

```bash
git add src/assurance/narrator.py src/api_v2.py tests/test_narrator.py
git commit -m "refactor: Narrator usa LLMProvider intercambiable"
```

---

### Task 7: `build_root_cause_prompt` (puro)

**Files:**
- Create: `src/assurance/root_cause.py`
- Test: `tests/test_root_cause_prompt.py`

- [ ] **Step 1: Write the failing test** — `tests/test_root_cause_prompt.py`:

```python
from src.assurance.root_cause import build_root_cause_prompt


def _failures(n):
    return [{"test_name": f"t{i}", "error_type": "TimeoutException",
             "message": f"esperando elemento {i}", "trace": f"at Foo.java:{i}",
             "project": "proj-a" if i % 2 else "proj-b"} for i in range(n)]


def test_prompt_includes_family_and_samples():
    fam = {"title": "Timeout de login", "occurrence_count": 12}
    prompt = build_root_cause_prompt(fam, _failures(3))
    assert "Timeout de login" in prompt
    assert "12" in prompt
    assert "proj-a" in prompt and "proj-b" in prompt
    assert "## Causa raíz" in prompt and "## Pasos sugeridos" in prompt


def test_prompt_truncates_to_six_failures():
    fam = {"title": "X", "occurrence_count": 99}
    prompt = build_root_cause_prompt(fam, _failures(20))
    # only 6 sample lines (each starts with "- test=")
    assert prompt.count("- test=") == 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_root_cause_prompt.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.assurance.root_cause'`

- [ ] **Step 3: Write `src/assurance/root_cause.py`:**

```python
from typing import Any, Dict, List

_MAX_FAILURES = 6


def _top_frame(trace: str) -> str:
    for line in (trace or "").splitlines():
        s = line.strip()
        if s.startswith("at ") or " line " in s or 'File "' in s:
            return s
    return ""


def build_root_cause_prompt(family: Dict[str, Any], failures: List[Dict[str, Any]]) -> str:
    """Construye el prompt de causa raíz (puro, sin LLM)."""
    projects = sorted({f.get("project") for f in failures if f.get("project")})
    lines = []
    for f in failures[:_MAX_FAILURES]:
        lines.append(
            f"- test={f.get('test_name')} tipo={f.get('error_type')} "
            f"msg={(f.get('message') or '')[:300]} frame={_top_frame(f.get('trace'))}"
        )
    samples = "\n".join(lines)
    return (
        "Eres un ingeniero de QA senior. Analiza esta familia de defectos y propon la causa raiz "
        "mas probable y pasos de correccion. SOLO ves sintomas (mensajes y trazas), no el codigo "
        "fuente, asi que tus pasos son heuristicos.\n\n"
        f"Familia: {family.get('title')}\n"
        f"Ocurrencias: {family.get('occurrence_count')} | Proyectos: {', '.join(projects) or 'n/d'}\n"
        f"Muestra de fallos:\n{samples}\n\n"
        "Responde en espanol, en markdown, con exactamente estas dos secciones:\n"
        "## Causa raíz\n(1-3 frases)\n## Pasos sugeridos\n(3-5 pasos numerados)"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_root_cause_prompt.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/assurance/root_cause.py tests/test_root_cause_prompt.py
git commit -m "feat: build_root_cause_prompt (prompt puro de causa raíz)"
```

---

### Task 8: `RootCauseAnalyzer`

**Files:**
- Modify: `src/assurance/root_cause.py`
- Test: `tests/test_root_cause_analyzer.py`

- [ ] **Step 1: Write the failing test** — `tests/test_root_cause_analyzer.py`:

```python
from src.assurance.root_cause import RootCauseAnalyzer


class _FakeProvider:
    def __init__(self, out):
        self.out = out
        self.prompt = None

    def complete(self, prompt: str) -> str:
        self.prompt = prompt
        return self.out


def test_analyze_calls_provider_and_strips_think():
    p = _FakeProvider("<think>razonando</think>## Causa raíz\nTimeouts de red")
    analyzer = RootCauseAnalyzer(p)
    out = analyzer.analyze({"title": "Timeout", "occurrence_count": 5},
                           [{"test_name": "t", "error_type": "TimeoutException",
                             "message": "m", "trace": "at A.java:1", "project": "p"}])
    assert out == "## Causa raíz\nTimeouts de red"
    assert "Timeout" in p.prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_root_cause_analyzer.py -v`
Expected: FAIL with `ImportError: cannot import name 'RootCauseAnalyzer'`

- [ ] **Step 3: Append to `src/assurance/root_cause.py`** (add the import and the class):

At the top, change the imports to include the provider/reasoning:
```python
from typing import Any, Dict, List

from src.llm.provider import LLMProvider
from src.llm.reasoning import strip_reasoning
```
At the end of the file, add:
```python
class RootCauseAnalyzer:
    """Genera causa raíz + pasos de fix para una familia, vía un LLMProvider."""

    def __init__(self, provider: LLMProvider):
        self._provider = provider

    def analyze(self, family: Dict[str, Any], failures: List[Dict[str, Any]]) -> str:
        prompt = build_root_cause_prompt(family, failures)
        return strip_reasoning(self._provider.complete(prompt))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_root_cause_analyzer.py tests/test_root_cause_prompt.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/assurance/root_cause.py tests/test_root_cause_analyzer.py
git commit -m "feat: RootCauseAnalyzer (LLM + strip_reasoning)"
```

---

### Task 9: Repositorio — `get_family_with_failures`, `save_root_cause`, lineage con root_cause

**Files:**
- Modify: `src/defects/repository.py`
- Test: `tests/test_root_cause_repository.py` (integration)

- [ ] **Step 1: Write the failing test** — `tests/test_root_cause_repository.py`:

```python
import os
import uuid

import pytest

pytestmark = pytest.mark.integration

from dotenv import load_dotenv

load_dotenv()

import psycopg  # noqa: E402

from src.defects.repository import AssuranceRepository, IngestItem  # noqa: E402
from src.ingest.models import FailureRecord  # noqa: E402
from src.defects.fingerprint import fingerprint  # noqa: E402

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture
def repo():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    return AssuranceRepository(DBURL)


@pytest.fixture
def org():
    user_id = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                        " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                        (user_id, f"rc-{user_id[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s, %s) returning id",
                        ("rc-org-" + user_id[:8], user_id))
            org_id = str(cur.fetchone()[0])
        conn.commit()
    yield {"user_id": user_id, "org_id": org_id}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id = %s", (org_id,))
            cur.execute("delete from auth.users where id = %s", (user_id,))
        conn.commit()


def _ingest_one(repo, u, o):
    rec = FailureRecord(test_name="t", error_type="TimeoutException", message="boom 30000ms",
                        trace="at A.java:1", project="proj-a", source="allure")
    item = IngestItem(rec=rec, fingerprint=fingerprint(rec), embedding=[0.1] * 384)
    repo.ingest_run(user_id=u, org_id=o, project="proj-a", source="allure", items=[item])
    return repo.list_defects(user_id=u, org_id=o)[0]["id"]


def test_get_family_with_failures_and_save_root_cause(repo, org):
    u, o = org["user_id"], org["org_id"]
    fid = _ingest_one(repo, u, o)
    data = repo.get_family_with_failures(user_id=u, defect_id=fid)
    assert data is not None
    assert data["family"]["root_cause"] is None
    assert data["failures"] and data["failures"][0]["message"] == "boom 30000ms"
    assert repo.save_root_cause(user_id=u, defect_id=fid, text="## Causa raíz\nx") is True
    data2 = repo.get_family_with_failures(user_id=u, defect_id=fid)
    assert data2["family"]["root_cause"] == "## Causa raíz\nx"


def test_non_member_cannot_read_or_write(repo, org):
    u, o = org["user_id"], org["org_id"]
    fid = _ingest_one(repo, u, o)
    other = str(uuid.uuid4())
    assert repo.get_family_with_failures(user_id=other, defect_id=fid) is None
    assert repo.save_root_cause(user_id=other, defect_id=fid, text="x") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_root_cause_repository.py -m integration -v`
Expected: FAIL with `AttributeError: 'AssuranceRepository' object has no attribute 'get_family_with_failures'`

- [ ] **Step 3: Add two methods to `AssuranceRepository`** (after `get_lineage`):

```python
    def get_family_with_failures(self, *, user_id: str, defect_id: str):
        """Familia (con root_cause) + sus fallos recientes (con message/trace) para análisis.

        Devuelve None si la familia no existe o el usuario no es miembro del org.
        """
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select f.id, f.title, f.status, f.occurrence_count, f.root_cause
                    from public.defect_families f
                    where f.id = %s
                      and (f.scope = 'global' or exists (
                          select 1 from public.memberships m
                          where m.org_id = f.org_id and m.user_id = %s))
                    """,
                    (defect_id, user_id),
                )
                fam = cur.fetchone()
                if fam is None:
                    return None
                cur.execute(
                    """
                    select fl.test_name, fl.error_type, fl.message, fl.trace, r.project
                    from public.failures fl
                    join public.test_runs r on r.id = fl.run_id
                    where fl.defect_family_id = %s
                    order by fl.created_at desc
                    limit 20
                    """,
                    (defect_id,),
                )
                failures = [
                    {"test_name": r["test_name"], "error_type": r["error_type"],
                     "message": r["message"], "trace": r["trace"], "project": r["project"]}
                    for r in cur.fetchall()
                ]
            return {
                "family": {
                    "id": str(fam["id"]), "title": fam["title"], "status": fam["status"],
                    "occurrence_count": fam["occurrence_count"], "root_cause": fam["root_cause"],
                },
                "failures": failures,
            }

    def save_root_cause(self, *, user_id: str, defect_id: str, text: str) -> bool:
        """Persiste el análisis de causa raíz. Devuelve False si no es miembro / no existe."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update public.defect_families
                    set root_cause = %s
                    where id = %s
                      and (scope = 'global' or exists (
                          select 1 from public.memberships m
                          where m.org_id = public.defect_families.org_id and m.user_id = %s))
                    """,
                    (text, defect_id, user_id),
                )
                updated = cur.rowcount > 0
            conn.commit()
        return updated
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_root_cause_repository.py -m integration -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full unit suite (no regressions)**

Run: `python3 -m pytest -m "not integration" -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/defects/repository.py tests/test_root_cause_repository.py
git commit -m "feat: get_family_with_failures + save_root_cause (con membership)"
```

---

### Task 10: Modelos + endpoint `POST /v2/defects/{id}/root-cause`

**Files:**
- Modify: `src/multitenant_models.py`
- Modify: `src/api_v2.py`
- Test: `tests/test_api_v2_root_cause.py`

- [ ] **Step 1: Write the failing test** — `tests/test_api_v2_root_cause.py`:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api_v2 import router, get_current_user, get_assurance_repo, get_root_cause_analyzer


class _User:
    user_id = "u1"


FAM = {"family": {"id": "d1", "title": "T", "status": "open", "occurrence_count": 3,
                  "root_cause": None}, "failures": []}


class _Repo:
    def __init__(self, cached=None):
        FAM["family"]["root_cause"] = cached
        self.saved = None

    def get_family_with_failures(self, *, user_id, defect_id):
        return FAM if defect_id == "d1" else None

    def save_root_cause(self, *, user_id, defect_id, text):
        self.saved = text
        return True


class _Analyzer:
    def __init__(self, out="## Causa raíz\nx"):
        self.calls = 0
        self.out = out

    def analyze(self, family, failures):
        self.calls += 1
        if self.out is None:
            raise RuntimeError("LLM down")
        return self.out


def _client(repo, analyzer):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _User()
    app.dependency_overrides[get_assurance_repo] = lambda: repo
    app.dependency_overrides[get_root_cause_analyzer] = lambda: analyzer
    return TestClient(app)


def test_generates_and_caches():
    repo, analyzer = _Repo(cached=None), _Analyzer()
    r = _client(repo, analyzer).post("/v2/defects/d1/root-cause")
    assert r.status_code == 200
    body = r.json()
    assert body["cached"] is False and "Causa raíz" in body["root_cause"]
    assert repo.saved is not None and analyzer.calls == 1


def test_returns_cache_without_regenerating():
    repo, analyzer = _Repo(cached="## Causa raíz\ncacheado"), _Analyzer()
    r = _client(repo, analyzer).post("/v2/defects/d1/root-cause")
    assert r.json()["cached"] is True and analyzer.calls == 0


def test_regenerate_forces_new():
    repo, analyzer = _Repo(cached="viejo"), _Analyzer()
    r = _client(repo, analyzer).post("/v2/defects/d1/root-cause?regenerate=true")
    assert r.json()["cached"] is False and analyzer.calls == 1


def test_unknown_defect_404():
    r = _client(_Repo(), _Analyzer()).post("/v2/defects/nope/root-cause")
    assert r.status_code == 404


def test_llm_down_503():
    r = _client(_Repo(cached=None), _Analyzer(out=None)).post("/v2/defects/d1/root-cause")
    assert r.status_code == 503
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_v2_root_cause.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_root_cause_analyzer'`

- [ ] **Step 3: Add the Pydantic model** — append to `src/multitenant_models.py` (ensure `Optional` is imported):

```python
class RootCauseResponse(BaseModel):
    defect_id: str
    root_cause: str
    cached: bool
```
Also add `root_cause: Optional[str] = None` to the existing `DefectLineageResponse` model.

- [ ] **Step 4: Edit `src/api_v2.py`.**

(a) Add to imports: `from src.multitenant_models import RootCauseResponse` (merge into the existing multitenant_models import).

(b) Add a lazy dep + module global (next to `get_narrator`):
```python
_root_cause_analyzer = None


def get_root_cause_analyzer():
    global _root_cause_analyzer
    if _root_cause_analyzer is None:
        from src.assurance.root_cause import RootCauseAnalyzer
        from src.llm.factory import get_llm_provider
        _root_cause_analyzer = RootCauseAnalyzer(get_llm_provider())
    return _root_cause_analyzer
```

(c) Add the endpoint (after the existing `/defects/{defect_id}` lineage endpoint):
```python
@router.post("/defects/{defect_id}/root-cause", response_model=RootCauseResponse)
def root_cause_v2(
    defect_id: str,
    regenerate: bool = False,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: AssuranceRepository = Depends(get_assurance_repo),
    analyzer=Depends(get_root_cause_analyzer),
) -> RootCauseResponse:
    try:
        data = repo.get_family_with_failures(user_id=user.user_id, defect_id=defect_id)
        if data is None:
            raise HTTPException(status_code=404, detail="defecto no encontrado")
        cached = data["family"].get("root_cause")
        if cached and not regenerate:
            return RootCauseResponse(defect_id=defect_id, root_cause=cached, cached=True)
        text = analyzer.analyze(data["family"], data["failures"])
        repo.save_root_cause(user_id=user.user_id, defect_id=defect_id, text=text)
        return RootCauseResponse(defect_id=defect_id, root_cause=text, cached=False)
    except HTTPException:
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    except Exception as exc:  # noqa: BLE001 — fallo del LLM/proveedor
        raise HTTPException(status_code=503, detail="el análisis IA no está disponible") from exc
```

(d) In the existing `/defects/{defect_id}` lineage endpoint, include `root_cause` in the response (the `get_lineage` repo method returns a `family` dict; add `root_cause=lineage["family"].get("root_cause")` when constructing `DefectLineageResponse`). To make the data available, also add `f.root_cause` to the `get_lineage` SELECT and to its returned `family` dict in `src/defects/repository.py` (one column + one key).

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_api_v2_root_cause.py -v` (5 passed), then `python3 -m pytest -m "not integration" -q` (report count), then `python3 -c "import src.api_v2"` (exit 0).

- [ ] **Step 6: Commit**

```bash
git add src/multitenant_models.py src/api_v2.py src/defects/repository.py tests/test_api_v2_root_cause.py
git commit -m "feat: endpoint POST /v2/defects/{id}/root-cause + root_cause en lineage"
```

---

### Task 11: Frontend — botón de causa raíz

**Files:**
- Modify: `frontend/src/lib/api/types.ts`
- Modify: `frontend/src/lib/api/endpoints.ts`
- Modify: `frontend/src/app/app/defects/page.tsx`

- [ ] **Step 1: Add the type** — append to `frontend/src/lib/api/types.ts`:

```typescript
export interface RootCauseResponse {
  defect_id: string;
  root_cause: string;
  cached: boolean;
}
```

- [ ] **Step 2: Add the client function** — append to `frontend/src/lib/api/endpoints.ts` (mirror the existing `apiRequest` helper used by the other functions; read the file to use the real helper name):

```typescript
export async function analyzeRootCause(
  token: string,
  defectId: string,
  regenerate = false,
): Promise<RootCauseResponse> {
  return apiRequest<RootCauseResponse>(
    `/api/v2/defects/${encodeURIComponent(defectId)}/root-cause?regenerate=${regenerate}`,
    "POST",
    { token },
  );
}
```
(Import `RootCauseResponse`. If the real helper differs from `apiRequest`, mirror exactly how `analyzeRootCause`'s siblings call it.)

- [ ] **Step 3: Add the button + render in the lineage panel** of `frontend/src/app/app/defects/page.tsx`. In the `<Card>` that shows the lineage (where `lineageQuery.data?.family` is rendered), add below the failures list:

```tsx
{lineageQuery.data?.family && (
  <RootCausePanel token={accessToken!} defectId={lineageQuery.data.family.id} />
)}
```
And add this component at the bottom of the file (before the default export's closing, or as a separate component in the same file):

```tsx
function RootCausePanel({ token, defectId }: { token: string; defectId: string }) {
  const [text, setText] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(regenerate = false) {
    setBusy(true);
    setError(null);
    try {
      const r = await analyzeRootCause(token, defectId, regenerate);
      setText(r.root_cause);
    } catch {
      setError("No se pudo generar el análisis (¿LLM disponible?).");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 space-y-2 border-t border-zinc-100 pt-3">
      <Button onClick={() => run(false)} disabled={busy} className="text-xs">
        {busy ? "Analizando…" : "Analizar causa raíz"}
      </Button>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {text && (
        <div className="space-y-2">
          <p className="text-xs text-zinc-400">Sugerencia generada por IA — revísala.</p>
          <pre className="whitespace-pre-wrap rounded-lg bg-zinc-50 p-3 text-sm text-zinc-700">{text}</pre>
          <Button onClick={() => run(true)} disabled={busy} className="text-xs">Regenerar</Button>
        </div>
      )}
    </div>
  );
}
```
Add the needed imports at the top: `analyzeRootCause` from `@/lib/api/endpoints`, and ensure `useState` and `Button` are imported (they already are on this page). Reset `text` to `null` when `selected` changes is NOT required (the component remounts per family because it's keyed by the lineage family).

- [ ] **Step 4: Verify typecheck and lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: no errors. (Do NOT run `npm run build` — it hangs in this env. If `node_modules` is broken locally, skip and rely on CI; note it.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api/types.ts frontend/src/lib/api/endpoints.ts frontend/src/app/app/defects/page.tsx
git commit -m "feat: botón de análisis de causa raíz en Defect DNA"
```

---

### Task 12: Verificación e2e

**Files:** none (verification only)

- [ ] **Step 1: Full unit suite**

Run: `python3 -m pytest -m "not integration" -q`
Expected: all green (prior suite + new LLM/root-cause unit tests).

- [ ] **Step 2: Integration suite (requires `DATABASE_URL`)**

Run: `python3 -m pytest -m integration -q`
Expected: all green (incl. the new `test_root_cause_repository.py`).

- [ ] **Step 3: Smoke-test the factory across providers**

Run:
```bash
python3 -c "
from src import config
from src.llm.factory import get_llm_provider
from src.llm.providers.ollama import OllamaProvider
config.LLM_PROVIDER='ollama'
assert isinstance(get_llm_provider(), OllamaProvider)
print('factory OK (ollama default)')
"
```
Expected: `factory OK (ollama default)`

---

## Notas de implementación

- **TDD estricto**: cada componente RED → GREEN → commit. 4 espacios, sin tabs.
- **Imports lazy** de `openai`/`anthropic`/`langchain_ollama` dentro de los métodos: el despliegue on-prem mínimo (solo Ollama) no necesita las libs comerciales en runtime, aunque estén en requirements.
- **Default `ollama`**: sin configurar nada, sigue siendo 0 €/privado.
- **Frontend** evita `npm run build` (se cuelga en este entorno) y `react-markdown` (render simple con `whitespace-pre-wrap`); el CI valida typecheck/lint/build.
- **Orden**: 1 (config/deps) → 2-5 (capa LLM) → 6 (narrator) → 7-8 (causa raíz) → 9 (repo) → 10 (endpoint) → 11 (frontend) → 12 (verificación).

