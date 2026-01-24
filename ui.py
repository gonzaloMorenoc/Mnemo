import streamlit as st
import os
from src.loader import LogLoader
from src.vector_store import VectorStoreManager
from src.model import BugAnalyzer
from src.inspector import DatabaseInspector
from src.config import DATA_PATH

# Page configuration
st.set_page_config(
    page_title="Smart Error Debugger | QA Engine",
    page_icon="🚀",
    layout="wide"
)

# Custom CSS for a premium feel
st.markdown("""
    <style>
    .main {
        background-color: #f5f7f9;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        background-color: #007bff;
        color: white;
    }
    .stTextArea>div>div>textarea {
        background-color: #ffffff;
    }
    .reportview-container .main .block-container {
        padding-top: 2rem;
    }
    .status-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #e9ecef;
        margin-bottom: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

# Helper function to initialize components
@st.cache_resource
def get_components():
    loader = LogLoader()
    chunks = loader.load()
    vs_manager = VectorStoreManager()
    vectorstore = vs_manager.get_vectorstore(chunks if chunks else None)
    analyzer = BugAnalyzer(vectorstore)
    inspector = DatabaseInspector()
    return analyzer, inspector

def main():
    st.title("🚀 Smart Error Debugger")
    st.subheader("QA AI Engineer Assistant - Log & Bug Analysis")

    try:
        analyzer, inspector = get_components()
    except Exception as e:
        st.error(f"Error al inicializar el sistema: {e}")
        return

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configuración")
        st.info("Modelo: DeepSeek-R1:8b (Local)")
        
        # DB Status
        data = inspector.vectorstore.get()
        chunk_count = len(data.get('ids', []))
        st.metric("Documentos en DB", chunk_count)
        
        if st.button("🔄 Recargar Logs"):
            st.cache_resource.clear()
            st.rerun()

        st.divider()
        st.markdown("### 📘 Sobre el Sistema")
        st.write("Este asistente utiliza RAG (Retrieval-Augmented Generation) para buscar soluciones en tu histórico de logs.")

    # Main Interface
    col1, col2 = st.columns([1.5, 1])

    with col1:
        st.markdown("### 🔍 Analizar Nuevo Error")
        error_input = st.text_area(
            "Pega aquí el Log, Stack Trace o descripción del error:",
            height=250,
            placeholder="Ejemplo: Traceback (most recent call last): \n  File 'app.py', line 42, in main..."
        )

        if st.button("🚀 Iniciar Análisis de Causa Raíz"):
            if error_input.strip():
                with st.spinner("DeepSeek-R1 está razonando..."):
                    try:
                        response = analyzer.analyze(error_input)
                        
                        st.markdown("---")
                        st.markdown("### 📝 REPORTE DE LA IA")
                        
                        # Display results
                        result = response["result"]
                        
                        # If DeepSeek uses <thought> tags, we can try to separate them
                        if "</thought>" in result:
                            parts = result.split("</thought>")
                            thought = parts[0].replace("<thought>", "").strip()
                            final_answer = parts[1].strip()
                            
                            with st.expander("🤔 Ver Proceso de Razonamiento"):
                                st.write(thought)
                            st.success(final_answer)
                        else:
                            st.success(result)
                            
                    except Exception as e:
                        st.error(f"Error durante el análisis: {e}")
            else:
                st.warning("Por favor, introduce un log de error para analizar.")

    with col2:
        st.markdown("### 📚 Contexto Encontrado")
        st.write("Estos son los fragmentos históricos más similares:")
        
        if error_input.strip():
            # Get the retriever to show what was found
            search_results = analyzer.qa_chain.retriever.get_relevant_documents(error_input)
            for i, doc in enumerate(search_results):
                with st.expander(f"Resultado {i+1}: {os.path.basename(doc.metadata.get('source', 'Desconocido'))}"):
                    st.write(doc.page_content)
                    st.caption(f"Tipo: {doc.metadata.get('type', 'desconocido')}")
        else:
            st.info("Los resultados aparecerán aquí una vez realices una búsqueda.")

if __name__ == "__main__":
    main()
