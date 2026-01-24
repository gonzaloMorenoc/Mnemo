# Smart Error Debugger 🚀

Analizador de logs y buscador de errores avanzado diseñado para equipos de QA. Este proyecto utiliza técnicas de RAG (Retrieval-Augmented Generation) para contrastar nuevos errores con históricos y documentación técnica, ofreciendo soluciones basadas en inteligencia artificial local.

## Stack Tecnológico

El proyecto está construido sobre un stack moderno orientado a IA local y observabilidad:

- **LLM**: DeepSeek-R1 (8B) mediante **Ollama** (Reasoning Model).
- **Orquestación**: **LangChain** para la gestión de cadenas RAG.
- **Base de Datos Vectorial**: **ChromaDB** para almacenamiento persistente.
- **UI**: **Streamlit** para un dashboard interactivo y visual.
- **QA de la IA**: **RAGAS** para medir la fidelidad y relevancia de las respuestas.
- **Observabilidad**: Integración nativa con **LangSmith**.
- **Ingesta**: Soporta `.log`, `.json`, `.pdf`, `.md` y conectores API (**Jira/Confluence**).

## Estructura del código

El proyecto sigue una arquitectura modular y limpia:

- `ui.py`: Dashboard interactivo de Streamlit.
- `main.py`: Interfaz de línea de comandos (CLI).
- `src/loader.py`: Ingestión multifuente (Local, Jira, Confluence) con procesamiento inteligente.
- `src/evaluator.py`: Cálculo de métricas de calidad (Faithfulness y Relevancy).
- `src/vector_store.py`: Gestión de ChromaDB y Feedback Loop.
- `src/model.py`: Orquestación de DeepSeek y la cadena de recuperación.
- `src/inspector.py`: Herramienta para auditar el contenido de los vectores.

## 🛠️ Instalación y Configuración

1. **Modelos Locales**:
   ```bash
   ollama pull deepseek-r1:8b
   ```

2. **Dependencias**:
   ```bash
   pip3 install -r requirements.txt
   ```

3. **Variables de Entorno**: Configura tu archivo `.env` (usa `.env.example` como plantilla) con tus claves de LangSmith, Jira o Confluence.

## 🚀 Modo de uso

### Opción A: Interfaz Web (Recomendada)
Ofrece dashboard de calidad, visualización de razonamiento y feedback interactivo:
```bash
streamlit run ui.py
```

### Opción B: Consola (CLI)
Para pruebas rápidas en terminal:
```bash
python3 main.py
```

## ✨ Funcionalidades Avanzadas

- **Thought Visualization**: Visualiza el proceso de razonamiento interno de DeepSeek-R1 antes de dar la solución.
- **Quality Metrics**: Cada respuesta incluye métricas de "Fidelidad" para asegurar que la IA no alucina.
- **Feedback Loop**: Permite calificar las soluciones para mejorar el ranking de resultados en el futuro.
- **Multi-Source**: Combina tus logs locales con tickets de Jira y páginas de Confluence automáticamente.
