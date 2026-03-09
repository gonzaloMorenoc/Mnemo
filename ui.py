import streamlit as st
import os
import pandas as pd
from src.loader import LogLoader
from src.vector_store import VectorStoreManager
from src.model import BugAnalyzer
from src.inspector import DatabaseInspector
from src.evaluator import RAGASEvaluator
from src.history import HistoryManager

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Smart Error Debugger",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# GLOBAL CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
/* ── Base ── */
[data-testid="stAppViewContainer"] {
    background: #0d1117;
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] {
    background: #161b22;
    border-right: 1px solid #30363d;
}

/* ── Typography ── */
html, body, [class*="css"] {
    font-family: 'Inter', 'Segoe UI', sans-serif;
    color: #e6edf3;
}
h1, h2, h3, h4 { color: #f0f6fc !important; }

/* ── Tabs ── */
[data-testid="stTabs"] button {
    color: #8b949e;
    font-weight: 500;
    padding: 0.5rem 1.25rem;
    border-radius: 6px 6px 0 0;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #58a6ff !important;
    border-bottom: 2px solid #58a6ff !important;
    background: transparent !important;
}
[data-testid="stTabs"] [role="tablist"] {
    border-bottom: 1px solid #30363d;
    gap: 0.25rem;
}

/* ── Buttons ── */
[data-testid="stButton"] > button {
    background: linear-gradient(135deg, #238636, #2ea043);
    color: #ffffff;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    padding: 0.6rem 1.4rem;
    transition: all 0.2s ease;
    box-shadow: 0 2px 8px rgba(35,134,54,0.35);
}
[data-testid="stButton"] > button:hover {
    background: linear-gradient(135deg, #2ea043, #3fb950);
    box-shadow: 0 4px 16px rgba(35,134,54,0.5);
    transform: translateY(-1px);
}

/* ── Text Area ── */
[data-testid="stTextArea"] textarea {
    background: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 8px !important;
    color: #e6edf3 !important;
    font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
    font-size: 0.85rem !important;
}
[data-testid="stTextArea"] textarea:focus {
    border-color: #58a6ff !important;
    box-shadow: 0 0 0 3px rgba(88,166,255,0.15) !important;
}

/* ── Text Input ── */
[data-testid="stTextInput"] input {
    background: #161b22 !important;
    border: 1px solid #30363d !important;
    border-radius: 6px !important;
    color: #e6edf3 !important;
}
[data-testid="stTextInput"] input:focus {
    border-color: #58a6ff !important;
}

/* ── Expanders ── */
[data-testid="stExpander"] {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    margin-bottom: 0.5rem;
}
[data-testid="stExpander"] summary {
    color: #8b949e;
    font-size: 0.875rem;
}

/* ── Metrics ── */
[data-testid="stMetric"] {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 1rem 1.25rem;
}
[data-testid="stMetricLabel"] { color: #8b949e !important; font-size: 0.8rem !important; }
[data-testid="stMetricValue"] { color: #f0f6fc !important; font-size: 1.6rem !important; }

/* ── Spinner ── */
[data-testid="stSpinner"] { color: #58a6ff; }

/* ── Divider ── */
hr { border-color: #30363d !important; }

/* ── Alerts ── */
[data-testid="stAlert"] { border-radius: 8px; }

/* ── File uploader ── */
[data-testid="stFileUploader"] {
    background: #161b22;
    border: 2px dashed #30363d;
    border-radius: 10px;
    padding: 1rem;
    transition: border-color 0.2s;
}
[data-testid="stFileUploader"]:hover { border-color: #58a6ff; }

/* ── Form ── */
[data-testid="stForm"] {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 1.5rem;
}

/* ── Sidebar items ── */
[data-testid="stSidebarContent"] [data-testid="stMetric"] {
    background: #0d1117;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# HTML HELPERS
# ─────────────────────────────────────────────
def _badge(label: str, color: str = "#238636") -> str:
    return f"""<span style="
        background:{color}22; color:{color};
        border:1px solid {color}66;
        border-radius:20px; padding:2px 10px;
        font-size:0.75rem; font-weight:600;
    ">{label}</span>"""

def _score_color(value: float) -> str:
    if value >= 0.75:
        return "#3fb950"
    elif value >= 0.5:
        return "#d29922"
    return "#f85149"

def _metric_card(label: str, value: str, color: str, icon: str = "") -> str:
    return f"""
    <div style="
        background:#161b22; border:1px solid {color}55;
        border-left:3px solid {color};
        border-radius:10px; padding:1rem 1.25rem;
        margin-bottom:0.5rem;
    ">
        <div style="color:#8b949e; font-size:0.75rem; font-weight:600; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:0.3rem;">
            {icon} {label}
        </div>
        <div style="color:{color}; font-size:1.8rem; font-weight:700; line-height:1;">
            {value}
        </div>
    </div>"""

def _result_card(content: str) -> str:
    return f"""
    <div style="
        background:#161b22; border:1px solid #30363d;
        border-radius:12px; padding:1.5rem;
        line-height:1.7; color:#e6edf3;
        font-size:0.9rem; white-space:pre-wrap;
        font-family:'Inter','Segoe UI',sans-serif;
    ">{content}</div>"""

def _source_pill(source_type: str) -> str:
    colors = {
        "jira_bug": ("#0052cc", "Jira"),
        "json": ("#6e40c9", "JSON"),
        "pdf": ("#d29922", "PDF"),
        "external": ("#8b949e", "Ext"),
    }
    color, label = colors.get(source_type, ("#58a6ff", source_type.upper()))
    return _badge(label, color)

def _header():
    st.markdown("""
    <div style="
        background: linear-gradient(135deg, #161b22 0%, #1c2128 100%);
        border: 1px solid #30363d;
        border-radius: 14px;
        padding: 1.75rem 2rem;
        margin-bottom: 1.5rem;
        display: flex;
        align-items: center;
        gap: 1rem;
    ">
        <div style="font-size:2.5rem; line-height:1;">🔬</div>
        <div>
            <div style="font-size:1.6rem; font-weight:700; color:#f0f6fc; line-height:1.1;">
                Smart Error Debugger
            </div>
            <div style="color:#8b949e; font-size:0.875rem; margin-top:0.3rem;">
                QA AI Engineer Assistant &nbsp;·&nbsp; DeepSeek-R1 &nbsp;·&nbsp; Advanced RAG + Hybrid Search
            </div>
        </div>
        <div style="margin-left:auto; display:flex; gap:0.5rem; align-items:center;">
            <span style="
                background:#238636; color:#fff;
                border-radius:20px; padding:3px 12px;
                font-size:0.75rem; font-weight:600;
            ">● ONLINE</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# COMPONENTS INIT
# ─────────────────────────────────────────────
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

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    _header()

    try:
        analyzer, inspector, evaluator, vs_manager, history = get_components()
    except Exception as e:
        st.error(f"**Error al inicializar el sistema:** {e}")
        st.info("Asegúrate de que Ollama está corriendo y el modelo `deepseek-r1:8b` está disponible.")
        return

    # ── Session state defaults ──
    for key, default in [("last_docs", []), ("last_result", None), ("last_metrics", None)]:
        if key not in st.session_state:
            st.session_state[key] = default

    # ─────────────────────────────────────────
    # SIDEBAR
    # ─────────────────────────────────────────
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center; padding: 0.5rem 0 1rem;">
            <div style="font-size:1.1rem; font-weight:700; color:#f0f6fc;">⚙️ Panel de Control</div>
        </div>
        """, unsafe_allow_html=True)

        # Model info
        st.markdown("""
        <div style="
            background:#0d1117; border:1px solid #30363d;
            border-radius:8px; padding:0.75rem 1rem; margin-bottom:1rem;
        ">
            <div style="color:#8b949e; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.08em;">Modelo activo</div>
            <div style="color:#58a6ff; font-weight:600; font-size:0.9rem; margin-top:0.2rem;">DeepSeek-R1 : 8B</div>
            <div style="color:#8b949e; font-size:0.75rem;">Local via Ollama · Privado</div>
        </div>
        """, unsafe_allow_html=True)

        # Data sources
        st.markdown("<div style='color:#8b949e; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:0.5rem;'>Fuentes de datos</div>", unsafe_allow_html=True)

        from src.config import JIRA_URL, CONFLUENCE_URL
        sources = [
            ("📄 Logs locales (.log, .json)", True),
            ("📑 Documentación (.pdf, .md)", True),
            ("🎯 Jira API", bool(JIRA_URL)),
            ("📘 Confluence API", bool(CONFLUENCE_URL)),
        ]
        for label, active in sources:
            color = "#3fb950" if active else "#6e7681"
            dot = "●" if active else "○"
            st.markdown(f"""<div style="display:flex; justify-content:space-between; align-items:center;
                padding:0.35rem 0; border-bottom:1px solid #21262d; font-size:0.82rem;">
                <span style="color:#e6edf3;">{label}</span>
                <span style="color:{color}; font-size:0.9rem;">{dot}</span>
            </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Vector DB stats
        try:
            db_data = inspector.vectorstore.get()
            n_vecs = len(db_data.get('ids', []))
        except Exception:
            n_vecs = "–"

        st.markdown(f"""
        <div style="background:#0d1117; border:1px solid #30363d; border-radius:8px; padding:0.75rem 1rem; margin-bottom:1rem;">
            <div style="color:#8b949e; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.08em;">Base de conocimiento</div>
            <div style="color:#f0f6fc; font-size:1.6rem; font-weight:700;">{n_vecs}</div>
            <div style="color:#8b949e; font-size:0.75rem;">vectores indexados</div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🔄 Sincronizar todo", use_container_width=True):
            st.cache_resource.clear()
            st.session_state.last_docs = []
            st.session_state.last_result = None
            st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        # Quick stats from history
        stats = history.get_stats()
        if stats['total_analyses'] > 0:
            st.markdown("<div style='color:#8b949e; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:0.5rem;'>Estadísticas de sesión</div>", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            c1.metric("Análisis", stats['total_analyses'])
            c2.metric("Fidelidad", f"{stats['avg_faithfulness']*100:.0f}%")

    # ─────────────────────────────────────────
    # TABS
    # ─────────────────────────────────────────
    tab_analyzer, tab_history, tab_ingestion = st.tabs([
        "🔍  Analizador",
        "📊  Historial & Métricas",
        "⚙️  Gestión de Datos",
    ])

    # ═══════════════════════════════════════════
    # TAB 1 – ANALIZADOR
    # ═══════════════════════════════════════════
    with tab_analyzer:
        col_main, col_ctx = st.columns([3, 2], gap="large")

        with col_main:
            st.markdown("#### Introduce el error o log a analizar")
            error_input = st.text_area(
                label="",
                height=180,
                placeholder="Pega aquí el stack trace, mensaje de error o descripción del bug...\n\nEjemplo:\n  TimeoutException: Message: timeout\n  at selenium.webdriver.support.wait.WebDriverWait.until",
                key="error_input",
            )

            analyze_col, _ = st.columns([1, 2])
            with analyze_col:
                run = st.button("🚀 Analizar error", use_container_width=True)

            if run:
                if not error_input.strip():
                    st.warning("Por favor, introduce un error antes de analizar.")
                else:
                    # ── Progress ──
                    progress_bar = st.progress(0, text="Inicializando pipeline RAG...")

                    progress_bar.progress(15, text="🔎 Recuperando documentos relevantes (BM25 + Semántico)...")
                    docs = analyzer.qa_chain.retriever.invoke(error_input)
                    st.session_state.last_docs = docs
                    context_text = [d.page_content for d in docs]

                    progress_bar.progress(45, text="⚙️ Re-ranking con Cross-Encoder...")

                    progress_bar.progress(60, text="🧠 DeepSeek-R1 generando solución...")
                    raw_response = analyzer.qa_chain.combine_documents_chain.invoke({
                        "input_documents": docs,
                        "question": error_input,
                    })
                    result = raw_response.get("output_text", raw_response) if isinstance(raw_response, dict) else raw_response
                    st.session_state.last_result = result

                    progress_bar.progress(85, text="📊 Evaluando calidad (Faithfulness & Relevancy)...")
                    metrics = evaluator.evaluate_response(error_input, result, context_text)
                    if metrics is None:
                        metrics = {"faithfulness": 0.0, "relevancy": 0.0}
                    st.session_state.last_metrics = metrics

                    history.save_analysis(
                        error_input,
                        result,
                        metrics['faithfulness'],
                        metrics['relevancy'],
                        context_text,
                    )

                    progress_bar.progress(100, text="✅ Análisis completado")
                    progress_bar.empty()

            # ── Results ──
            if st.session_state.last_result:
                result = st.session_state.last_result
                metrics = st.session_state.last_metrics or {"faithfulness": 0.0, "relevancy": 0.0}
                docs = st.session_state.last_docs

                st.markdown("<br>", unsafe_allow_html=True)

                # Quality bar
                f_val = metrics['faithfulness']
                r_val = metrics['relevancy']
                f_color = _score_color(f_val)
                r_color = _score_color(r_val)

                m1, m2, m3 = st.columns(3)
                with m1:
                    st.markdown(_metric_card("Faithfulness", f"{f_val*100:.0f}%", f_color, "🎯"), unsafe_allow_html=True)
                with m2:
                    st.markdown(_metric_card("Relevancy", f"{r_val*100:.0f}%", r_color, "📌"), unsafe_allow_html=True)
                with m3:
                    sources_count = len(docs)
                    st.markdown(_metric_card("Fuentes usadas", str(sources_count), "#58a6ff", "📚"), unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)

                # Report
                st.markdown("""<div style="color:#8b949e; font-size:0.75rem; text-transform:uppercase;
                    letter-spacing:0.08em; margin-bottom:0.75rem; font-weight:600;">
                    📝 Reporte de análisis
                </div>""", unsafe_allow_html=True)

                if "</thought>" in result:
                    parts = result.split("</thought>")
                    analysis_text = parts[1].strip()
                    reasoning_text = parts[0].replace("<thought>", "").strip()

                    st.markdown(_result_card(analysis_text), unsafe_allow_html=True)
                    st.markdown("<br>", unsafe_allow_html=True)
                    with st.expander("🤔 Ver razonamiento interno de DeepSeek"):
                        st.markdown(f"""<div style="
                            background:#161b22; border-left:3px solid #6e40c9;
                            padding:1rem 1.25rem; border-radius:0 8px 8px 0;
                            font-family:monospace; font-size:0.8rem; color:#8b949e;
                            white-space:pre-wrap; line-height:1.6;
                        ">{reasoning_text}</div>""", unsafe_allow_html=True)
                else:
                    st.markdown(_result_card(result), unsafe_allow_html=True)

                # Feedback
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown("""<div style="color:#8b949e; font-size:0.8rem; margin-bottom:0.5rem;">
                    ¿Fue útil esta solución?
                </div>""", unsafe_allow_html=True)

                fb1, fb2, fb3 = st.columns([1, 1, 4])
                with fb1:
                    if st.button("👍 Útil", use_container_width=True):
                        for doc in docs:
                            doc_id = doc.metadata.get("id")
                            if doc_id:
                                vs_manager.update_feedback(doc_id, 1)
                        st.toast("¡Gracias! Feedback registrado.", icon="✅")
                with fb2:
                    if st.button("👎 Mejorar", use_container_width=True):
                        for doc in docs:
                            doc_id = doc.metadata.get("id")
                            if doc_id:
                                vs_manager.update_feedback(doc_id, -1)
                        st.toast("Entendido, lo tendremos en cuenta.", icon="📝")

        # ── Context column ──
        with col_ctx:
            st.markdown("#### Contexto recuperado")
            if st.session_state.last_docs:
                docs = st.session_state.last_docs
                st.markdown(f"""<div style="color:#8b949e; font-size:0.8rem; margin-bottom:0.75rem;">
                    {len(docs)} documento(s) recuperados y re-rankeados
                </div>""", unsafe_allow_html=True)
                for i, doc in enumerate(docs):
                    source_name = os.path.basename(doc.metadata.get('source', 'API externa'))
                    doc_type = doc.metadata.get('type', 'external')
                    rating = doc.metadata.get('rating', 0)
                    with st.expander(f"#{i+1}  {source_name}"):
                        st.markdown(_source_pill(doc_type), unsafe_allow_html=True)
                        if rating != 0:
                            r_color = "#3fb950" if rating > 0 else "#f85149"
                            st.markdown(f"<span style='color:{r_color}; font-size:0.75rem;'>Rating acumulado: {rating:+d}</span>", unsafe_allow_html=True)
                        st.markdown("<br>", unsafe_allow_html=True)
                        st.markdown(f"""<div style="
                            background:#0d1117; border-radius:6px; padding:0.75rem;
                            font-family:monospace; font-size:0.75rem; color:#8b949e;
                            max-height:200px; overflow-y:auto; line-height:1.5;
                            white-space:pre-wrap;
                        ">{doc.page_content[:600]}{"..." if len(doc.page_content) > 600 else ""}</div>""",
                        unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="
                    background:#161b22; border:2px dashed #30363d;
                    border-radius:12px; padding:3rem 1.5rem;
                    text-align:center; color:#6e7681;
                ">
                    <div style="font-size:2rem; margin-bottom:0.5rem;">📭</div>
                    <div style="font-size:0.875rem;">Analiza un error para ver<br>los documentos relacionados</div>
                </div>
                """, unsafe_allow_html=True)

    # ═══════════════════════════════════════════
    # TAB 2 – HISTORIAL & MÉTRICAS
    # ═══════════════════════════════════════════
    with tab_history:
        hist_data = history.get_history()
        stats = history.get_stats()

        # KPIs
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(_metric_card("Total análisis", str(stats['total_analyses']), "#58a6ff", "🔢"), unsafe_allow_html=True)
        with k2:
            fv = stats['avg_faithfulness']
            st.markdown(_metric_card("Fidelidad media", f"{fv*100:.1f}%", _score_color(fv), "🎯"), unsafe_allow_html=True)
        with k3:
            rv = stats['avg_relevancy']
            st.markdown(_metric_card("Relevancia media", f"{rv*100:.1f}%", _score_color(rv), "📌"), unsafe_allow_html=True)
        with k4:
            # Last analysis delta placeholder
            trend = "↑" if fv >= 0.7 else "↓"
            trend_color = "#3fb950" if fv >= 0.7 else "#f85149"
            st.markdown(_metric_card("Tendencia", trend, trend_color, "📈"), unsafe_allow_html=True)

        # Chart
        if hist_data and len(hist_data) > 1:
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("""<div style="color:#8b949e; font-size:0.75rem; text-transform:uppercase;
                letter-spacing:0.08em; margin-bottom:0.75rem; font-weight:600;">
                Evolución de la calidad
            </div>""", unsafe_allow_html=True)
            df = pd.DataFrame(hist_data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp')
            chart_data = df.set_index('timestamp')[['faithfulness', 'relevancy']]
            st.line_chart(chart_data, color=["#58a6ff", "#3fb950"], height=220)

        # History list
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("""<div style="color:#8b949e; font-size:0.75rem; text-transform:uppercase;
            letter-spacing:0.08em; margin-bottom:0.75rem; font-weight:600;">
            Historial reciente
        </div>""", unsafe_allow_html=True)

        if not hist_data:
            st.markdown("""
            <div style="
                background:#161b22; border:2px dashed #30363d;
                border-radius:12px; padding:3rem; text-align:center; color:#6e7681;
            ">
                <div style="font-size:2rem; margin-bottom:0.5rem;">📋</div>
                <div>Aún no hay análisis registrados.</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            for item in hist_data:
                f_c = _score_color(item['faithfulness'])
                r_c = _score_color(item['relevancy'])
                error_preview = item['error_input'][:70].replace('\n', ' ')
                label = f"🕒 {item['timestamp']}  ·  {error_preview}{'...' if len(item['error_input']) > 70 else ''}"
                with st.expander(label):
                    h1, h2 = st.columns([3, 1])
                    with h1:
                        st.markdown("**Error original**")
                        st.code(item['error_input'], language="text")
                        st.markdown("**Análisis**")
                        st.markdown(f"""<div style="
                            background:#0d1117; border-left:3px solid #58a6ff;
                            padding:0.75rem 1rem; border-radius:0 6px 6px 0;
                            font-size:0.85rem; color:#e6edf3; white-space:pre-wrap;
                            line-height:1.6;
                        ">{item['analysis_result']}</div>""", unsafe_allow_html=True)
                    with h2:
                        st.markdown(f"""
                        <div style="background:#161b22; border:1px solid #30363d; border-radius:8px; padding:1rem; margin-bottom:0.75rem;">
                            <div style="color:#8b949e; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.06em;">Faithfulness</div>
                            <div style="color:{f_c}; font-size:1.4rem; font-weight:700;">{item['faithfulness']*100:.0f}%</div>
                        </div>
                        <div style="background:#161b22; border:1px solid #30363d; border-radius:8px; padding:1rem;">
                            <div style="color:#8b949e; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.06em;">Relevancy</div>
                            <div style="color:{r_c}; font-size:1.4rem; font-weight:700;">{item['relevancy']*100:.0f}%</div>
                        </div>
                        """, unsafe_allow_html=True)

                        md_report = f"""# Reporte de Error — {item['timestamp']}

## Error
```
{item['error_input']}
```

## Análisis
{item['analysis_result']}

---
**Métricas de Calidad**
- Faithfulness: {item['faithfulness']*100:.1f}%
- Relevancy: {item['relevancy']*100:.1f}%
"""
                        st.markdown("<br>", unsafe_allow_html=True)
                        st.download_button(
                            label="📥 Descargar MD",
                            data=md_report,
                            file_name=f"reporte_{item['id']}.md",
                            mime="text/markdown",
                            key=f"dl_{item['id']}",
                            use_container_width=True,
                        )

    # ═══════════════════════════════════════════
    # TAB 3 – GESTIÓN DE DATOS
    # ═══════════════════════════════════════════
    with tab_ingestion:
        ing_col, cfg_col = st.columns([3, 2], gap="large")

        with ing_col:
            st.markdown("""<div style="color:#8b949e; font-size:0.75rem; text-transform:uppercase;
                letter-spacing:0.08em; margin-bottom:0.75rem; font-weight:600;">
                📥 Subir documentación
            </div>""", unsafe_allow_html=True)

            uploaded_files = st.file_uploader(
                "Arrastra o selecciona archivos",
                accept_multiple_files=True,
                type=["log", "pdf", "md", "json"],
                help="Formatos: .log (trazas crudas), .pdf/.md (documentación), .json (casos de éxito)",
            )

            st.markdown("""
            <div style="
                display:flex; gap:0.5rem; flex-wrap:wrap; margin: 0.5rem 0 1rem;
            ">
                <span style="background:#1c2128; border:1px solid #30363d; color:#8b949e; border-radius:6px; padding:3px 10px; font-size:0.75rem;">.log — Trazas crudas</span>
                <span style="background:#1c2128; border:1px solid #30363d; color:#8b949e; border-radius:6px; padding:3px 10px; font-size:0.75rem;">.pdf — Documentación</span>
                <span style="background:#1c2128; border:1px solid #30363d; color:#8b949e; border-radius:6px; padding:3px 10px; font-size:0.75rem;">.md — Manuales</span>
                <span style="background:#1c2128; border:1px solid #30363d; color:#8b949e; border-radius:6px; padding:3px 10px; font-size:0.75rem;">.json — Casos de éxito</span>
            </div>
            """, unsafe_allow_html=True)

            if st.button("💾 Guardar y procesar archivos", use_container_width=False):
                if uploaded_files:
                    from src.config import DATA_PATH
                    os.makedirs(DATA_PATH, exist_ok=True)
                    for uf in uploaded_files:
                        with open(os.path.join(DATA_PATH, uf.name), "wb") as f:
                            f.write(uf.getbuffer())
                    st.success(f"✅ {len(uploaded_files)} archivo(s) guardado(s). Usa **Sincronizar todo** en el sidebar para indexarlos.")
                else:
                    st.warning("Selecciona al menos un archivo primero.")

        with cfg_col:
            st.markdown("""<div style="color:#8b949e; font-size:0.75rem; text-transform:uppercase;
                letter-spacing:0.08em; margin-bottom:0.75rem; font-weight:600;">
                🔌 Fuentes externas
            </div>""", unsafe_allow_html=True)

            from src.config import JIRA_URL, JIRA_USERNAME, CONFLUENCE_URL

            with st.form("external_sources_form"):
                st.markdown("""<div style="color:#8b949e; font-size:0.8rem; margin-bottom:1rem;">
                    Credenciales guardadas en memoria durante esta sesión.
                </div>""", unsafe_allow_html=True)

                st.markdown("**Jira**")
                new_jira_url = st.text_input("URL", value=JIRA_URL or "", placeholder="https://yourorg.atlassian.net", key="jira_url")
                new_jira_user = st.text_input("Usuario", value=JIRA_USERNAME or "", placeholder="user@company.com", key="jira_user")
                new_jira_token = st.text_input("API Token", type="password", placeholder="••••••••••", key="jira_token")

                st.markdown("<br>**Confluence**", unsafe_allow_html=True)
                new_conf_url = st.text_input("URL", value=CONFLUENCE_URL or "", placeholder="https://yourorg.atlassian.net/wiki", key="conf_url")

                if st.form_submit_button("✅ Guardar conexiones", use_container_width=True):
                    os.environ["JIRA_URL"] = new_jira_url
                    os.environ["JIRA_USERNAME"] = new_jira_user
                    if new_jira_token:
                        os.environ["JIRA_API_TOKEN"] = new_jira_token
                    os.environ["CONFLUENCE_URL"] = new_conf_url
                    st.success("Configuración actualizada. Usa **Sincronizar todo** para aplicar.")
                    st.cache_resource.clear()


if __name__ == "__main__":
    main()
