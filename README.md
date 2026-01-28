# Smart Error Debugger

Analizador de logs y buscador de errores avanzado diseñado para equipos de QA. Este proyecto utiliza un motor RAG (Retrieval-Augmented Generation) optimizado para entornos de debugging, contrastando nuevos errores con históricos y documentación técnica.

## Stack Tecnologico

El proyecto esta construido sobre un stack moderno orientado a IA local y observabilidad:

- LLM: DeepSeek-R1 (8B) mediante Ollama (Reasoning Model).
- Backend API: FastAPI para exponer el motor de inferencia como servicio REST.
- Orquestacion: LangChain para la gestion de cadenas RAG.
- Recuperacion Avanzada:
  - Busqueda Hibrida: EnsembleRetriever combinando logica vectorial (ChromaDB) y palabras clave (BM25).
  - Re-ranking: Cross-Encoder (BGE-Reranker) para reordenar resultados segun relevancia.
- UI: Streamlit para un dashboard interactivo con gestion de datos integrada.
- QA de la IA: RAGAS para medir la fidelidad y relevancia de las respuestas.
- Historial: SQLite para la persistencia de analisis y metricas.
- Ingesta: Soporta .log, .json, .pdf, .md y conectores API (Jira/Confluence).

## Diagrama de Arquitectura

![Arquitectura del Proyecto](doc/arq.png)

## Estructura del codigo

El proyecto sigue una arquitectura modular API-First:

- api.py: API REST construida con FastAPI que expone endpoints de analisis y sincronizacion.
- ui.py: Dashboard interactivo que permite analisis, visualizacion de historico y gestion de datos.
- src/retriever.py: Fabrica del recuperador avanzado (BM25 + Chroma + Reranker).
- src/loader.py: Ingestion multifuente (Local, Jira, Confluence) con chunking optimizado para logs.
- src/evaluator.py: Calculo de metricas de calidad (Faithfulness y Relevancy).
- src/vector_store.py: Gestion de ChromaDB (Local y Remote).
- src/model.py: Orquestacion de DeepSeek y la cadena de cuestion-respuesta.
- src/history.py: Capa de persistencia en SQLite.

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

### Opcion A: Interfaz Web (Dashboard)
Ofrece analisis visual, gestion de archivos drag-and-drop y configuracion de fuentes:
```bash
streamlit run ui.py
```

### Opcion B: API REST (Backend)
Ideal para integraciones o desacoplar el motor de ia:
```bash
uvicorn api:app --reload
```
Documentacion interactiva disponible en: http://localhost:8000/docs

### Opcion C: Docker
Levanta todo el stack (Ollama, ChromaDB y UI) con un solo comando:
```bash
docker-compose up --build
```

## Funcionalidades Avanzadas

### Motor de Busqueda Hibrida
A diferencia de un RAG estandar, este sistema utiliza BM25 para capturar codigos de error exactos (ej: 0x8004210B) combinandolo con embeddings semanticos.

### Re-ranking Neural
Los resultados preliminares pasan por un modelo Cross-Encoder que lee y reordena los documentos, asegurando que el contexto enviado al LLM sea el mas pertinente.

### Gestion de Datos en UI
Nueva pestaña "Gestion de Datos" que permite subir logs y documentación desde el navegador, asi como configurar credenciales de Jira/Confluence en caliente sin reiniciar el servidor.

### Metricas de Calidad
Cada respuesta incluye scores de Fidelidad (Faithfulness) y Relevancia calculados por RAGAS para auditar el desempeño de la IA.
