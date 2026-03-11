# Smart Error Debugger

Analizador de logs y buscador de errores avanzado diseñado para equipos de QA. Este proyecto utiliza un motor RAG (Retrieval-Augmented Generation) optimizado para entornos de debugging, contrastando nuevos errores con historicos y documentacion tecnica.

## Stack Tecnologico

El proyecto esta construido sobre un stack moderno orientado a IA local y observabilidad:

- **LLM**: DeepSeek-R1 (8B) mediante Ollama (Reasoning Model).
- **Backend API**: FastAPI para exponer el motor de inferencia como servicio REST.
- **Orquestacion**: LangChain para la gestion de cadenas RAG.
- **Recuperacion Avanzada**:
  - Busqueda Hibrida: EnsembleRetriever combinando logica vectorial (ChromaDB) y palabras clave (BM25).
  - Re-ranking: Cross-Encoder (BGE-Reranker) para reordenar resultados segun relevancia.
- **UI**: Streamlit para un dashboard interactivo con gestion de datos integrada.
- **Evaluacion (QA de la IA)**: RAGAS 0.4.x con 4 metricas (Faithfulness, Relevancy, Context Precision, Context Recall).
- **Testing**: pytest con suite de tests unitarios e integracion para validar la calidad del pipeline RAG.
- **Historial**: SQLite para la persistencia de analisis y metricas.
- **Ingesta**: Soporta .log, .json, .pdf, .md y conectores API (Jira/Confluence).

## Diagrama de Arquitectura

![Arquitectura del Proyecto](doc/arq.png)

## Estructura del codigo

El proyecto sigue una arquitectura modular API-First:

```
SmartErrorDebugger/
├── api.py                  # API REST (FastAPI) - endpoints de analisis, evaluacion y sincronizacion
├── ui.py                   # Dashboard interactivo (Streamlit) - analisis, historico, gestion de datos
├── main.py                 # CLI entry point
├── src/
│   ├── evaluator.py        # Evaluador RAGAS con 4 metricas via LLM local (Ollama)
│   ├── retriever.py        # Recuperador avanzado (BM25 + Chroma + Cross-Encoder Reranker)
│   ├── loader.py           # Ingestion multifuente (Local, Jira, Confluence)
│   ├── model.py            # Orquestacion de DeepSeek y cadena QA
│   ├── vector_store.py     # Gestion de ChromaDB (Local y Remote)
│   ├── history.py          # Persistencia SQLite con 4 metricas RAGAS
│   ├── inspector.py        # Utilidad de inspeccion de base de datos vectorial
│   ├── config.py           # Configuracion centralizada y variables de entorno
│   └── prompts.py          # Templates de prompts para QA Engineer
├── tests/
│   ├── conftest.py         # Fixtures compartidos para pytest
│   └── test_evaluation.py  # Suite de tests: 13 unit + 3 integration
├── data/
│   ├── qa_test_errors.json # Datos de test (errores QA de ejemplo)
│   └── eval_dataset.json   # Dataset de evaluacion con ground truth (8 casos)
├── pytest.ini              # Configuracion de pytest y markers
├── requirements.txt        # Dependencias del proyecto
├── Dockerfile
├── docker-compose.yml
└── .env.example            # Template de variables de entorno
```

## Instalacion y Configuracion

1. Modelos Locales:
   ```bash
   ollama pull deepseek-r1:8b
   ```

2. Dependencias:
   ```bash
   pip3 install -r requirements.txt
   ```

3. Variables de Entorno: Configura tu archivo `.env` (usa `.env.example` como plantilla) con tus claves de LangSmith, Jira o Confluence.

## Modo de uso

### Opcion A: Interfaz Web (Dashboard)
Ofrece analisis visual, gestion de archivos drag-and-drop y configuracion de fuentes:
```bash
streamlit run ui.py
```

### Opcion B: API REST (Backend)
Ideal para integraciones o desacoplar el motor de IA:
```bash
uvicorn api:app --reload
```
Documentacion interactiva disponible en: `http://localhost:8000/docs`

### Opcion C: Docker
Levanta todo el stack (Ollama, ChromaDB y UI) con un solo comando:
```bash
docker-compose up --build
```

## Evaluacion y Testing con RAGAS

El sistema integra RAGAS 0.4.x como framework de evaluacion para medir objetivamente la calidad del pipeline RAG. Todas las metricas se calculan en tiempo real usando el LLM local (DeepSeek-R1 via Ollama), sin depender de APIs externas como OpenAI.

### Metricas RAGAS

Cada respuesta generada se evalua automaticamente con 4 metricas:

| Metrica | Descripcion | Pregunta que responde |
|---------|-------------|----------------------|
| **Faithfulness** | Mide si la respuesta esta fundamentada en el contexto recuperado | ¿La IA se inventa informacion o usa los documentos? |
| **Response Relevancy** | Evalua si la respuesta es pertinente a la pregunta del usuario | ¿La respuesta realmente aborda el error consultado? |
| **Context Precision** | Verifica que los documentos recuperados sean relevantes | ¿El retriever trajo documentos utiles o ruido? |
| **Context Recall** | Mide si se recupero toda la informacion necesaria | ¿Se omitio algun documento critico para la respuesta? |

### Dataset de Evaluacion

El archivo `data/eval_dataset.json` contiene 8 casos de test con errores reales de QA/Selenium, cada uno con:
- **question**: El error a analizar (TimeoutException, StaleElementReferenceException, etc.)
- **ground_truth**: La respuesta esperada de referencia
- **contexts**: Los documentos de contexto relevantes

Este dataset permite ejecutar evaluaciones batch para medir la calidad general del sistema.

### Ejecutar Tests

```bash
# Tests unitarios (no requieren Ollama, usan mocks)
pytest tests/test_evaluation.py -v -m "not integration"

# Tests de integracion (requieren Ollama con deepseek-r1:8b activo)
pytest tests/test_evaluation.py -v -m integration

# Todos los tests
pytest -v
```

### Evaluacion Batch via API

El endpoint `POST /evaluate` ejecuta la evaluacion RAGAS sobre todo el dataset de test y devuelve scores por muestra y promedios agregados:

```bash
curl -X POST http://localhost:8000/evaluate
```

Respuesta:
```json
{
  "per_sample": [...],
  "averages": {
    "avg_faithfulness": 0.85,
    "avg_relevancy": 0.88,
    "avg_context_precision": 0.82,
    "avg_context_recall": 0.79
  },
  "total_samples": 8
}
```

### Suite de Tests

La suite en `tests/test_evaluation.py` cubre:

- **TestEvalDataset** (5 tests): Valida estructura, campos y contenido del dataset de evaluacion.
- **TestEvaluatorInit** (3 tests): Verifica inicializacion correcta del evaluador y sus 4 metricas.
- **TestEvaluatorOutputFormat** (4 tests): Asegura formato de salida, rangos validos [0,1] y fallback graceful.
- **TestBatchEvaluation** (1 test): Valida la evaluacion batch sobre el dataset completo.
- **TestRAGASIntegration** (3 tests): Tests end-to-end con LLM real (requieren Ollama).

## Endpoints de la API

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| `POST` | `/analyze` | Analiza un error log y devuelve diagnostico con 4 metricas RAGAS |
| `POST` | `/evaluate` | Ejecuta evaluacion batch RAGAS sobre el dataset de test |
| `POST` | `/sync` | Sincroniza y reindexza todas las fuentes de datos |
| `GET` | `/history` | Obtiene historial de analisis con metricas |
| `GET` | `/stats` | Estadisticas agregadas (promedios de las 4 metricas) |
| `GET` | `/health` | Health check del servicio |

## Funcionalidades Avanzadas

### Motor de Busqueda Hibrida
A diferencia de un RAG estandar, este sistema utiliza BM25 para capturar codigos de error exactos (ej: `0x8004210B`) combinandolo con embeddings semanticos. Los pesos (40% BM25, 60% semantico) estan optimizados para logs tecnicos.

### Re-ranking Neural
Los resultados preliminares pasan por un modelo Cross-Encoder (`BAAI/bge-reranker-base`) que lee y reordena los documentos, filtrando a los top 5 mas relevantes antes de enviarlos al LLM.

### Gestion de Datos en UI
Pestaña "Gestion de Datos" que permite subir logs y documentacion desde el navegador, asi como configurar credenciales de Jira/Confluence en caliente sin reiniciar el servidor.

### Dashboard de Calidad
El dashboard muestra en tiempo real las 4 metricas RAGAS por cada analisis, ademas de graficos de tendencia historica con promedios de Faithfulness, Relevancy, Context Precision y Context Recall.
