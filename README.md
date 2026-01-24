# Smart Error Debugger

Analizador de logs y buscador de errores avanzado diseñado para equipos de QA. Este proyecto utiliza técnicas de RAG (Retrieval-Augmented Generation) para contrastar nuevos errores con históricos y documentación técnica, ofreciendo soluciones basadas en inteligencia artificial local.

## Stack Tecnologico

El proyecto esta construido sobre un stack moderno orientado a IA local y observabilidad:

- LLM: DeepSeek-R1 (8B) mediante Ollama (Reasoning Model).
- Orquestacion: LangChain para la gestion de cadenas RAG.
- Base de Datos Vectorial: ChromaDB para almacenamiento persistente.
- UI: Streamlit para un dashboard interactivo y visual con sistema de pestañas.
- QA de la IA: RAGAS para medir la fidelidad y relevancia de las respuestas.
- Historial: SQLite para la persistencia de analisis y metricas.
- Ingesta: Soporta .log, .json, .pdf, .md y conectores API (Jira/Confluence).

## Estructura del codigo

El proyecto sigue una arquitectura modular y limpia:

- ui.py: Dashboard interactivo de Streamlit con Analizador y Dashboard de historial.
- main.py: Interfaz de linea de comandos (CLI).
- src/loader.py: Ingestion multifuente (Local, Jira, Confluence) con procesamiento inteligente.
- src/evaluator.py: Calculo de metricas de calidad (Faithfulness y Relevancy).
- src/vector_store.py: Gestion de ChromaDB (Local y Remote) y Feedback Loop.
- src/model.py: Orquestacion de DeepSeek y la cadena de recuperacion.
- src/history.py: Gestion del historial de analisis y persistencia de datos.

## Instalacion y Configuracion

1. Modelos Locales:
   ```bash
   ollama pull deepseek-r1:8b
   ```

2. Dependencias:
   ```bash
   pip3 install -r requirements.txt
   ```

3. Variables de Entorno: Configura tu archivo .env (usa .env.example como plantilla) con tus claves de LangSmith, Jira o Confluence.

## Modo de uso

### Opcion A: Interfaz Web (Recomendada)
Ofrece dashboard de calidad, visualizacion de razonamiento, historial de analisis y feedback interactivo:
```bash
streamlit run ui.py
```

### Opcion B: Consola (CLI)
Para pruebas rapidas en terminal:
```bash
python3 main.py
```

### Opcion C: Docker
Levanta todo el stack (Ollama, ChromaDB y UI) con un solo comando:
```bash
docker-compose up --build
```
Nota: La primera vez descargara el modelo DeepSeek-R1 automaticamente mediante el servicio ollama-pull.

## Dataset de Errores QA
Se ha incluido un dataset inicial en data/qa_test_errors.json con ejemplos reales de:
- Timeouts de Selenium
- Stale Element Exceptions
- Fallos de conexion de API
- Errores de asercion de negocio

## Funcionalidades Avanzadas

- Thought Visualization: Visualiza el proceso de razonamiento interno de DeepSeek-R1 antes de dar la solucion.
- Quality Metrics: Cada respuesta incluye metricas de Fidelidad para asegurar que la IA no alucina.
- History & Dashboard: Pestaña dedicada para ver la evolucion de la calidad y el total de analisis realizados.
- Professional Export: Permite descargar reportes tecnicos de cada error en formato Markdown.
- Feedback Loop: Permite calificar las soluciones para mejorar el ranking de resultados en el futuro.
- Multi-Source: Combina logs locales con tickets de Jira y paginas de Confluence automaticamente.
