import streamlit as st
import os
from src.loader import LogLoader
from src.vector_store import VectorStoreManager
from src.model import BugAnalyzer
from src.inspector import DatabaseInspector
from src.evaluator import RAGASEvaluator
from src.history import HistoryManager
import pandas as pd

# Page configuration
st.set_page_config(
    page_title="Smart Error Debugger | QA Engine",
    page_icon="🚀",
    layout="wide"
)

# Custom CSS for a premium feel
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    .metric-card { background-color: #ffffff; padding: 1rem; border-radius: 0.5rem; border: 1px solid #e1e4e8; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# Helper function to initialize components
@st.cache_resource
def get_components():
    loader = LogLoader()
    chunks = loader.load()
    vs_manager = VectorStoreManager()
    vectorstore = vs_manager.get_vectorstore(chunks if chunks else None)
    analyzer = BugAnalyzer(vectorstore, chunks=chunks)
    inspector = DatabaseInspector()
    evaluator = RAGASEvaluator()
    history = HistoryManager()
    return analyzer, inspector, evaluator, vs_manager, history

def main():
    st.title("🚀 Smart Error Debugger")
    st.subheader("QA AI Engineer Assistant - Advanced RAG & Evaluation")

    try:
        analyzer, inspector, evaluator, vs_manager, history = get_components()
    except Exception as e:
        st.error(f"Error al inicializar el sistema: {e}")
        return

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configuración")
        st.info(f"Modelo: DeepSeek-R1 (Local)")
        
        # Sources Status
        st.markdown("### 🔌 Fuentes de Datos")
        st.checkbox("Local Logs (.log, .json)", value=True, disabled=True)
        st.checkbox("Documentación (.pdf, .md)", value=True, disabled=True)
        
        from src.config import JIRA_URL, CONFLUENCE_URL
        st.checkbox("Jira API", value=bool(JIRA_URL))
        st.checkbox("Confluence API", value=bool(CONFLUENCE_URL))

        # DB Metrics
        st.divider()
        data = inspector.vectorstore.get()
        st.metric("Vectores en Memoria", len(data.get('ids', [])))
        
        if st.button("🔄 Sincronizar Todo"):
            st.cache_resource.clear()
            st.rerun()

    # Main Interface
    # Tabs for different views
    tab_analyzer, tab_history = st.tabs(["🔍 Analizador", "📊 Dashboard & Historial"])

    with tab_analyzer:
        col1, col2 = st.columns([1.5, 1])

        with col1:
            st.markdown("### 🔍 Analizar Nuevo Error")
            error_input = st.text_area(
                "Introduce log o descripción:",
                height=200,
                placeholder="Ejemplo: NullPointerException at line 45 in AuthService.py",
                key="error_input"
            )

            if st.button("🚀 Analizar"):
                if error_input.strip():
                    with st.spinner("DeepSeek está analizando e inspeccionando el historial..."):
                        # 1. Retrieval
                        docs = analyzer.qa_chain.retriever.invoke(error_input)
                        context_text = [d.page_content for d in docs]
                        
                        # 2. Generation
                        # Optimization: Use already retrieved docs to avoid re-running Reranker
                        with st.spinner("Generando solución..."):
                            raw_response = analyzer.qa_chain.combine_documents_chain.invoke({
                                "input_documents": docs,
                                "question": error_input
                            })
                            # Handle different output formats
                            result = raw_response.get("output_text", raw_response) if isinstance(raw_response, dict) else raw_response
                            response = {"result": result}
                        
                        # 3. Evaluation (RAGAS)
                        metrics = evaluator.evaluate_response(error_input, result, context_text)
                        
                        # 4. Save to History
                        history.save_analysis(
                            error_input, 
                            result, 
                            metrics['faithfulness'], 
                            metrics['relevancy'], 
                            context_text
                        )
                        
                        st.markdown("---")
                        
                        # Dashboard de Calidad (QA de la IA)
                        q_col1, q_col2, q_col3 = st.columns(3)
                        with q_col1:
                            st.metric("Faithfulness", f"{metrics['faithfulness']*100:.1f}%", help="¿La IA se inventa cosas o usa los logs?")
                        with q_col2:
                            st.metric("Relevancy", f"{metrics['relevancy']*100:.1f}%", help="¿La respuesta es útil para el error?")
                        with q_col3:
                            st.success("Analizado con DeepSeek-R1")

                        st.markdown("### 📝 REPORTE DE ANÁLISIS")
                        if "</thought>" in result:
                            parts = result.split("</thought>")
                            st.info(parts[1].strip())
                            with st.expander("🤔 Ver Razonamiento Interno"):
                                st.write(parts[0].replace("<thought>", "").strip())
                        else:
                            st.success(result)
                        
                        # 5. Feedback Loop
                        st.divider()
                        st.write("¿Fue útil esta solución?")
                        f_col1, f_col2 = st.columns([1, 5])
                        with f_col1:
                            if st.button("👍 Sí"):
                                st.toast("¡Gracias! Feedback registrado para mejorar el ranking.")
                        with f_col2:
                             if st.button("👎 No"):
                                 st.toast("Entendido, ajustaremos el contexto.")

        with col2:
            st.markdown("### 📚 Contexto & Evidencias")
            if error_input.strip():
                docs = analyzer.qa_chain.retriever.invoke(error_input)
                for i, doc in enumerate(docs):
                    source_name = os.path.basename(doc.metadata.get('source', 'External API'))
                    rating = doc.metadata.get('rating', 0)
                    with st.expander(f"📖 {source_name} (⭐ {rating})"):
                        st.write(doc.page_content)
                        st.caption(f"Tipo: {doc.metadata.get('type', 'external')}")
            else:
                st.info("Escribe algo para ver los documentos relacionados.")

    with tab_history:
        hist_data = history.get_history()
        st.markdown("### 📊 Métricas de Rendimiento")
        stats = history.get_stats()
        
        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.metric("Total Análisis", stats['total_analyses'])
        m_col2.metric("Fidelidad Media", f"{stats['avg_faithfulness']*100:.1f}%")
        m_col3.metric("Relevancia Media", f"{stats['avg_relevancy']*100:.1f}%")

        # Trend Chart
        if hist_data:
            df = pd.DataFrame(hist_data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp')
            
            st.markdown("#### Evolución de la Calidad")
            chart_data = df.set_index('timestamp')[['faithfulness', 'relevancy']]
            st.line_chart(chart_data)

        st.divider()
        st.markdown("### 📜 Historial Reciente")
        
        if not hist_data:
            st.info("Aún no hay análisis registrados.")
        else:
            for item in hist_data:
                with st.expander(f"🕒 {item['timestamp']} | Error: {item['error_input'][:50]}..."):
                    st.markdown("#### Error Original")
                    st.code(item['error_input'])
                    
                    st.markdown("#### Análisis DeepSeek")
                    st.write(item['analysis_result'])
                    
                    st.markdown("---")
                    col_ev1, col_ev2, col_ev3 = st.columns(3)
                    col_ev1.write(f"**Faithfulness:** {item['faithfulness']*100:.1f}%")
                    col_ev2.write(f"**Relevancy:** {item['relevancy']*100:.1f}%")
                    
                    # Markdown Export
                    md_report = f"""# Reporte de Error - {item['timestamp']}
## Error
{item['error_input']}

## Análisis
{item['analysis_result']}

---
**Métricas de Calidad:**
- Faithfulness: {item['faithfulness']*100:.1f}%
- Relevancy: {item['relevancy']*100:.1f}%
"""
                    st.download_button(
                        label="📥 Descargar Reporte (MD)",
                        data=md_report,
                        file_name=f"reporte_error_{item['id']}.md",
                        mime="text/markdown",
                        key=f"dl_{item['id']}"
                    )

if __name__ == "__main__":
    main()
