# Deep Dive Tecnico: Arquitectura del pipeline RAG legacy (pre-Mnemo)

Este documento desglosa la implementacion tecnica del proyecto a nivel de codigo, explicando los componentes criticos y los patrones de diseño utilizados en cada modulo.

## 1. Gestion Cuantica de Conocimiento: Ingesta y Fragmentacion

El modulo `src/loader.py` es el responsable de normalizar los datos de entrada.

### Implementacion de Chunking
Utilizamos `RecursiveCharacterTextSplitter` para asegurar que los fragmentos mantengan coherencia estructural, priorizando saltos de linea y espacios.

```python
self.text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=2500, 
    chunk_overlap=500
)
```

**Justificacion Tecnica**: Un `chunk_size` de 2500 caracteres es optimo para logs tecnicos, ya que permite capturar el mensaje de error junto con su traza de pila (stack trace) completa y los logs de contexto adyacentes. El solapamiento de 500 caracteres previene la perdida de informacion si un error ocurre justo en el limite de un fragmento.

## 2. Motor de Recuperacion Hibrida (Hybrid Search)

Ubicado en `src/retriever.py`, este es el componente mas avanzado del sistema. Combina busqueda semantica y busqueda por palabras clave.

### Implementacion del EnsembleRetriever
```python
# Busqueda Semantica (Vectores)
semantic_retriever = self.vectorstore.as_retriever(search_kwargs={"k": 10})

# Busqueda de Palabras Clave (BM25)
bm25_retriever = BM25Retriever.from_documents(self.chunks)
bm25_retriever.k = 10

# Union Hibrida
ensemble_retriever = EnsembleRetriever(
    retrievers=[bm25_retriever, semantic_retriever],
    weights=[0.4, 0.6]
)
```

**Analisis**: El sistema asigna un peso de 0.6 a la busqueda semantica y 0.4 a BM25. Esto equilibra la capacidad de encontrar "conceptos similares" con la capacidad de localizar identificadores unicos o codigos de error hexadecimales exactos.

## 3. Post-procesamiento: Re-ranking con Cross-Encoders

Para filtrar el ruido de la busqueda inicial, implementamos un modelo de re-ranking que actua como un segundo filtro mas inteligente.

```python
# Inicializacion del Cross-Encoder
model = HuggingFaceCrossEncoder(model_name="BAAI/bge-reranker-base")
compressor = CrossEncoderReranker(model=model, top_n=5)

# Creacion del Retriever con Compresion
compression_retriever = ContextualCompressionRetriever(
    base_compressor=compressor, 
    base_retriever=ensemble_retriever
)
```

**Funcionamiento**: Mientras que los recuperadores iniciales (Chroma y BM25) son rapidos pero menos precisos, el Cross-Encoder lee cada par (pregunta, documento) y calcula una puntuacion de relevancia real. Solo los 5 documentos mejor calificados llegan finalmente al LLM.

## 4. Orquestacion del Analisis (The Inference Chain)

El modulo `src/model.py` integra el motor recuperador con el modelo de razonamiento DeepSeek-R1.

```python
self.qa_chain = RetrievalQA.from_chain_type(
    llm=self.llm,
    chain_type="stuff",
    retriever=my_retriever,
    chain_type_kwargs={"prompt": PROMPT}
)
```

El prompt utilizado (`src/prompts.py`) define el comportamiento del sistema:
```python
QA_ENGINEER_TEMPLATE = """
Eres un QA Automation Engineer experto en debugging. Utiliza los siguientes fragmentos de logs historicos 
y soluciones previas para analizar el nuevo error...
CONTEXTO DE ERRORES PREVIOS: {context}
NUEVO ERROR A ANALIZAR: {question}
"""
```

## 5. Capa de Servicio: API REST (FastAPI)

En `api.py`, desacoplamos la logica de inferencia para permitir integraciones externas.

```python
@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_error(request: AnalysisRequest):
    docs = state.analyzer.qa_chain.retriever.invoke(request.error_log)
    
    # Optimizacion: Evitamos llamar a la cadena completa para reutilizar los docs recuperados
    raw_response = state.analyzer.qa_chain.combine_documents_chain.invoke({
        "input_documents": docs,
        "question": request.error_log
    })
    
    # Medicion de metricas automatica
    metrics = state.evaluator.evaluate_response(request.error_log, result, context_text)
    ...
```

**Detalle Tecnico**: Note la optimizacion donde invocamos directamente `combine_documents_chain`. Esto es crucial porque el `retriever` ya ha realizado el re-ranking pesado. Re-ejecutar la cadena completa duplicaria el tiempo de respuesta innecesariamente.

## 6. Evaluacion con RAGAS 0.4.x

El modulo `src/evaluator.py` implementa evaluacion real del pipeline RAG utilizando el framework RAGAS con LLMs locales via Ollama. Esto reemplaza la version anterior que retornaba metricas simuladas con `random.uniform()`.

### Arquitectura del Evaluador

```python
from ragas import evaluate, EvaluationDataset, SingleTurnSample
from ragas.metrics import Faithfulness, ResponseRelevancy, LLMContextPrecisionWithoutReference, LLMContextRecall
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper

class RAGASEvaluator:
    def __init__(self, model_name=MODEL_NAME):
        self.llm = LangchainLLMWrapper(
            OllamaLLM(model=model_name, base_url=OLLAMA_BASE_URL)
        )
        self.embeddings = LangchainEmbeddingsWrapper(
            OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL)
        )
        self.metrics = [
            Faithfulness(llm=self.llm),
            ResponseRelevancy(llm=self.llm, embeddings=self.embeddings),
            LLMContextPrecisionWithoutReference(llm=self.llm),
            LLMContextRecall(llm=self.llm),
        ]
```

**Detalle Tecnico**: RAGAS requiere un LLM para calcular sus metricas (actua como "juez"). Usamos `LangchainLLMWrapper` para adaptar `OllamaLLM` al formato que RAGAS espera, eliminando la dependencia de OpenAI. El mismo modelo DeepSeek-R1 que genera respuestas tambien evalua la calidad.

### Las 4 Metricas

| Metrica | Clase RAGAS | Que mide |
|---------|------------|----------|
| **Faithfulness** | `Faithfulness` | Verifica que cada afirmacion de la respuesta este respaldada por el contexto recuperado. Descompone la respuesta en claims y verifica cada uno contra los documentos. |
| **Response Relevancy** | `ResponseRelevancy` | Genera preguntas a partir de la respuesta y mide su similitud semantica con la pregunta original usando embeddings. Requiere tanto LLM como embeddings. |
| **Context Precision** | `LLMContextPrecisionWithoutReference` | Evalua si los documentos recuperados contienen informacion relevante, sin necesitar ground truth. Usa el LLM para juzgar cada fragmento. |
| **Context Recall** | `LLMContextRecall` | Mide si el contexto recuperado cubre toda la informacion necesaria para responder. Compara contra una referencia cuando esta disponible. |

### Evaluacion en Tiempo Real (Single Response)

Cada vez que un usuario analiza un error, el sistema ejecuta evaluacion automatica:

```python
def evaluate_response(self, question, answer, contexts, reference=None):
    sample = SingleTurnSample(
        user_input=question,
        response=answer,
        retrieved_contexts=contexts,
        reference=reference or "",
    )
    dataset = EvaluationDataset(samples=[sample])
    result = evaluate(dataset=dataset, metrics=self.metrics)
    scores = result.to_pandas().iloc[0].to_dict()
    return {
        "faithfulness": scores.get("faithfulness", 0.0),
        "relevancy": scores.get("response_relevancy", 0.0),
        "context_precision": scores.get("llm_context_precision_without_reference", 0.0),
        "context_recall": scores.get("llm_context_recall", 0.0),
    }
```

**Manejo de errores**: Si el LLM no esta disponible o RAGAS falla, el metodo retorna `0.0` para todas las metricas en lugar de romper el flujo del usuario.

### Evaluacion Batch (Dataset Completo)

Para testing sistematico, `evaluate_dataset()` procesa `data/eval_dataset.json` de una sola vez:

```python
def evaluate_dataset(self, dataset_path=None):
    # Carga 8 casos de test con ground truth
    # Construye EvaluationDataset con todos los samples
    # Retorna scores individuales + promedios agregados
```

El dataset contiene 8 errores reales de QA/Selenium con:
- `question`: El error completo (TimeoutException, StaleElementReferenceException, etc.)
- `ground_truth`: La solucion de referencia esperada
- `contexts`: Documentos de contexto relevantes

Este endpoint esta expuesto via `POST /evaluate` en la API REST.

## 7. Testing con pytest

La suite de tests en `tests/test_evaluation.py` valida el pipeline de evaluacion a dos niveles:

### Tests Unitarios (sin Ollama)

Usan mocks para verificar la logica sin necesitar el LLM:

- **TestEvalDataset** (5 tests): Valida que `eval_dataset.json` existe, tiene al menos 5 muestras, estructura correcta (`question`, `ground_truth`, `contexts`), contextos son listas no vacias, y ningun campo esta vacio.
- **TestEvaluatorInit** (3 tests): Verifica que el evaluador se importa correctamente, crea exactamente 4 metricas, e incluye `Faithfulness` y `ResponseRelevancy`.
- **TestEvaluatorOutputFormat** (4 tests): Valida que la salida tiene las 4 claves esperadas, valores en rango [0, 1], retorna zeros en caso de fallo, y acepta parametro `reference`.
- **TestBatchEvaluation** (1 test): Verifica la estructura de retorno de `evaluate_dataset()` (per_sample, averages, total_samples).

### Tests de Integracion (con Ollama)

Marcados con `@pytest.mark.integration`, requieren Ollama corriendo:

- **test_single_evaluation_real**: Ejecuta evaluacion real y verifica formato y rangos.
- **test_faithfulness_high_for_grounded_answer**: Una respuesta que viene directamente del contexto debe tener faithfulness alto (>= 0.5).
- **test_relevancy_low_for_irrelevant_answer**: Una respuesta completamente irrelevante ("receta de paella") debe tener relevancy bajo (< 0.7).

### Ejecucion

```bash
# Solo unitarios (rapido, CI-friendly)
pytest tests/test_evaluation.py -v -m "not integration"

# Solo integracion (requiere Ollama)
pytest tests/test_evaluation.py -v -m integration
```

## 8. Persistencia y Observabilidad (History Manager)

Utilizamos SQLite en `src/history.py` para registrar la entrada/salida y las 4 metricas RAGAS.

```python
def save_analysis(self, error_input, result, faithfulness, relevancy, context,
                  context_precision=0.0, context_recall=0.0):
    cursor.execute("""
        INSERT INTO analysis_history
        (timestamp, error_input, analysis_result, faithfulness, relevancy,
         context_precision, context_recall, context)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (...))
```

### Esquema de la tabla

```sql
CREATE TABLE analysis_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME,
    error_input TEXT,
    analysis_result TEXT,
    faithfulness REAL,
    relevancy REAL,
    context_precision REAL DEFAULT 0.0,
    context_recall REAL DEFAULT 0.0,
    context TEXT  -- JSON serializado
);
```

**Migracion automatica**: El constructor detecta bases de datos antiguas (sin las columnas `context_precision`/`context_recall`) y las migra automaticamente via `ALTER TABLE`, garantizando compatibilidad hacia atras.

Las estadisticas agregadas (`get_stats()`) retornan promedios de las 4 metricas para el dashboard de tendencias.

## 9. Gestion de Configuracion

El archivo `src/config.py` centraliza los parametros criticos:
- `MODEL_NAME`: El modelo de razonamiento local (`deepseek-r1:8b`).
- `OLLAMA_BASE_URL`: URL del servidor Ollama (usado por el evaluador y el modelo).
- `EMBEDDING_MODEL`: Modelo de generacion de vectores (`all-MiniLM-L6-v2`), compartido entre el retriever y el evaluador RAGAS.
- `DB_PATH`: Directorio de persistencia de ChromaDB.
- Credenciales de API para conectores externos (Jira, Confluence).

## Conclusion

La arquitectura del pipeline RAG legacy esta diseñada bajo el principio de "calidad sobre cantidad". Cada componente (BM25, Reranker, RAGAS Evaluator) ha sido seleccionado para mitigar los fallos comunes de los sistemas RAG basicos. La integracion de RAGAS con 4 metricas reales, respaldada por una suite de tests automatizados, convierte la evaluacion en un proceso medible y repetible, proporcionando confianza objetiva en la calidad de las respuestas del sistema.
