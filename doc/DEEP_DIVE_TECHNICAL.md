# Deep Dive Técnico: Arquitectura de Smart Error Debugger

Este documento desglosa la implementación técnica del proyecto a nivel de código, explicando los componentes críticos, los patrones de diseño y las decisiones de ingeniería de cada módulo.

---

## 1. Ingesta y Fragmentación (`src/loader.py`)

### Chunking optimizado para logs técnicos

```python
self.text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=2500,
    chunk_overlap=500
)
```

**Justificación**: Un `chunk_size` de 2500 caracteres permite capturar el mensaje de error junto con su stack trace completo. El solapamiento de 500 caracteres evita la pérdida de información cuando un error ocurre justo en el límite de un fragmento.

### Soporte de JSON arrays y objetos

El loader distingue entre JSON arrays (múltiples entradas) y objetos simples:

```python
def _process_json_file(self, file_path):
    data = json.load(f)
    if isinstance(data, list):
        return [self._process_json_entry(entry, file_path) for entry in data if isinstance(entry, dict)]
    elif isinstance(data, dict):
        return [self._process_json_entry(data, file_path)]
```

Cada entrada se normaliza al formato `Error / Stack Trace / Solution`, optimizando la legibilidad para el LLM.

---

## 2. Motor de Recuperación Híbrida (`src/retriever.py`)

### Arquitectura de 4 etapas

```
Input Query
    │
    ▼
┌─────────────────────────────────────────────┐
│  Etapa 1: BM25Retriever (k=10)              │  ← Coincidencias exactas
│  Etapa 2: Chroma SemanticRetriever (k=10)   │  ← Comprensión semántica
│             ↓ EnsembleRetriever             │
│          Pesos: [0.4 BM25, 0.6 Semantic]    │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  Etapa 3: BGE Cross-Encoder Re-ranking      │  ← Top-5 por relevancia real
│  model: BAAI/bge-reranker-base              │
└─────────────────────────────────────────────┘
    │
    ▼
  top-5 docs → LLM
```

**Análisis de pesos**: BM25 (0.4) captura identificadores únicos y códigos de error hexadecimales que el modelo semántico puede no representar bien. El modelo semántico (0.6) aporta comprensión del contexto y sinónimos técnicos.

---

## 3. Modelo de Embeddings (`src/config.py`)

### Migración a bge-base-en-v1.5

```python
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"  # 768 dims
# Anterior: "all-MiniLM-L6-v2"              # 384 dims
```

**Motivación**: `bge-base-en-v1.5` supera a `all-MiniLM-L6-v2` en benchmarks de recuperación técnica (MTEB). Con 768 dimensiones, captura matices semánticos más finos en código, mensajes de excepción y documentación técnica.

**Importante**: Al cambiar el modelo de embeddings, las dimensiones de los vectores cambian. Es necesario eliminar `db_chroma/` y reconstruir el índice. `VectorStoreManager` detecta y notifica este mismatch:

```python
try:
    self._vectorstore = Chroma(persist_directory=self.db_path, ...)
    self._vectorstore.get(limit=1)  # Validates dimension compatibility
    return self._vectorstore
except Exception as e:
    print(f"[VectorStore] Could not load existing DB: {e}\n  Delete '{self.db_path}/' and re-sync.")
    raise
```

---

## 4. Query Rewriting (`src/model.py`)

### El problema de los stack traces como queries

Un stack trace de 30 líneas es un query semántico pésimo: contiene rutas absolutas, IDs de sesión, números de línea y valores temporales que generan ruido en el espacio de embeddings.

### Solución: reescritura previa al retrieval

```python
def rewrite_query(self, error_log: str) -> str:
    """Transforma un stack trace ruidoso en una query semántica compacta."""
    prompt = _REWRITE_PROMPT.format(error=error_log[:2000])
    rewritten = self.llm.invoke(prompt).strip()
    if rewritten and len(rewritten) < 300:
        return rewritten
    return error_log  # Fallback: usar el input original
```

El prompt instruye al modelo a:
- Preservar nombres de excepciones y códigos de error
- Omitir rutas de archivo, números de línea e IDs de sesión
- Comprimir a 1-2 frases el problema central

**Mejora esperada**: 20-30% de mejora en recall para logs con alta densidad de ruido.

---

## 5. Generación con Streaming (`src/model.py`)

### Diferencia con la implementación anterior

```python
# Antes (bloqueante):
raw_response = analyzer.qa_chain.combine_documents_chain.invoke({...})
result = raw_response.get("output_text", raw_response)

# Ahora (streaming token a token):
def stream(self, docs: list, question: str):
    context = "\n\n---\n\n".join(doc.page_content for doc in docs)
    formatted_prompt = PROMPT.format(context=context, question=question)
    for chunk in self.llm.stream(formatted_prompt):
        yield chunk
```

### UX del streaming en la UI

La UI distingue dos fases del modelo DeepSeek-R1:

1. **Fase de razonamiento** (`<thought>...</thought>`): se muestra un panel compacto con el razonamiento interno en tiempo real
2. **Fase de respuesta**: la solución aparece token a token en el área principal

```python
for chunk in analyzer.stream(docs, error_input):
    full_result += chunk
    if "</thought>" in full_result:
        # Show reasoning + build answer in real time
    elif "<thought>" in full_result:
        # Show reasoning progress
    else:
        # Direct answer (no thought tags)
        answer_ph.markdown(full_result + " ▌")
```

---

## 6. Capa de Servicio: API REST (`api.py`)

### Ciclo de vida con lifespan (FastAPI moderno)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    state.lock = asyncio.Lock()
    await asyncio.to_thread(initialize_system)  # No bloquea el event loop
    yield

app = FastAPI(lifespan=lifespan)
```

**Detalles técnicos**:
- `on_event("startup")` está deprecated desde FastAPI 0.93 → sustituido por `lifespan`
- `initialize_system()` es síncrono y pesado (carga modelos HuggingFace) → se ejecuta en thread pool con `asyncio.to_thread()`
- El endpoint `/sync` usa `asyncio.Lock` para evitar race conditions si se invoca durante un análisis activo

### Pipeline de análisis en el endpoint

```python
@app.post("/analyze")
async def analyze_error(request: AnalysisRequest):
    # 1. Query rewriting (en thread para no bloquear)
    rewritten = await asyncio.to_thread(state.analyzer.rewrite_query, request.error_log)
    # 2. Retrieval híbrido (BM25 + Semantic + Reranker)
    docs = state.analyzer.qa_chain.retriever.invoke(rewritten)
    # 3. Generación (streaming colapsado para respuesta HTTP)
    result = "".join(state.analyzer.stream(docs, request.error_log))
    # 4. Evaluación + persistencia
    ...
```

---

## 7. Evaluación de Calidad (`src/evaluator.py`)

### Heurística token-overlap

```python
# Faithfulness: ¿cuánto de la respuesta está soportado por el contexto?
answer_tokens = set(answer_lower.split())
context_tokens = set(combined_context.split())
faithfulness = len(answer_tokens & context_tokens) / max(len(answer_tokens), 1)

# Relevancy: ¿la respuesta aborda los términos de la pregunta?
question_tokens = set(question_lower.split())
relevancy = len(question_tokens & answer_tokens) / max(len(question_tokens), 1)
```

**Limitaciones conocidas**: La heurística penaliza sinónimos y recompensa respuestas que copian texto irrelevante. Para producción, el sistema está preparado para RAGAS con LLM-as-judge (ver comentarios en `src/evaluator.py`).

---

## 8. Persistencia (`src/history.py`)

SQLite registra cada análisis con sus métricas para auditoría y tendencias:

```sql
CREATE TABLE analysis_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME,
    error_input TEXT,
    analysis_result TEXT,
    faithfulness REAL,
    relevancy REAL,
    context TEXT  -- JSON serializado de los documentos usados
)
```

La UI genera gráficos de evolución de calidad usando Pandas sobre esta tabla.

---

## 9. Suite de Tests (`tests/`)

### Filosofía de testing

Los tests están diseñados para ejecutarse sin dependencias externas (Ollama, ChromaDB). Los tests de integración que sí las requieren están marcados con `@pytest.mark.integration`.

### Golden Dataset como ground truth

El archivo `data/qa_test_errors.json` contiene 5 errores canónicos de QA con soluciones conocidas. Los tests de `test_golden_dataset.py` validan que:

1. Los 5 errores se cargan correctamente como Documents
2. Los nombres de excepción clave están indexados (necesario para BM25)
3. Los términos de solución están preservados en los chunks
4. El formato `Error/Stack Trace/Solution` es correcto

Esto crea un **regression gate**: si un cambio en el loader o el chunker rompe la indexación, los tests fallan antes de que la calidad del retrieval se degrade silenciosamente.

```bash
# Ejecutar todos los tests
pytest

# Solo tests unitarios (sin servicios externos)
pytest -m "not integration"

# Ver cobertura por módulo
pytest -v tests/
```

---

## Conclusión

La arquitectura de Smart Error Debugger está diseñada bajo el principio de **calidad sobre cantidad**. Cada componente mitiga un fallo específico de los sistemas RAG básicos:

| Fallo RAG básico | Solución implementada |
|---|---|
| Stack traces son malos queries semánticos | Query Rewriting pre-retrieval |
| Embeddings genéricos pierden precisión técnica | `bge-base-en-v1.5` (768 dims) |
| Búsqueda semántica pierde códigos exactos | BM25 en ensemble híbrido |
| Mucho ruido en los top-10 candidatos | Cross-Encoder re-ranking (top-5) |
| Respuesta bloqueante degrada UX | Streaming token-a-token |
| Sin regresión al cambiar el pipeline | Test suite con golden dataset |
| Métricas sin auditoría | SQLite + dashboard de tendencias |
