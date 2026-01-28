from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uvicorn
import os

from src.loader import LogLoader
from src.vector_store import VectorStoreManager
from src.model import BugAnalyzer
from src.evaluator import RAGASEvaluator
from src.history import HistoryManager
from src.inspector import DatabaseInspector

# Data Models
class AnalysisRequest(BaseModel):
    error_log: str

class AnalysisResponse(BaseModel):
    result: str
    metrics: Dict[str, float]
    context: List[str]
    analysis_id: Optional[int] = None

class FeedbackRequest(BaseModel):
    analysis_id: int
    rating: int # 1 (useful) or -1 (not useful)

# App & State
app = FastAPI(title="Smart Error Debugger API", version="1.0.0")

class AppState:
    analyzer: Optional[BugAnalyzer] = None
    history: Optional[HistoryManager] = None
    evaluator: Optional[RAGASEvaluator] = None
    inspector: Optional[DatabaseInspector] = None

state = AppState()

def initialize_system():
    print("Initializing System Components...")
    loader = LogLoader()
    chunks = loader.load()
    
    vs_manager = VectorStoreManager()
    vectorstore = vs_manager.get_vectorstore(chunks if chunks else None)
    
    state.analyzer = BugAnalyzer(vectorstore, chunks=chunks)
    state.history = HistoryManager()
    state.evaluator = RAGASEvaluator()
    state.inspector = DatabaseInspector()
    print("System Ready.")

@app.on_event("startup")
async def startup_event():
    initialize_system()

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_error(request: AnalysisRequest):
    if not state.analyzer:
        raise HTTPException(status_code=503, detail="System not initialized")
    
    # 1. Retrieve
    # We invoke the retriever created by AdvancedRetrieverFactory inside BugAnalyzer
    docs = state.analyzer.qa_chain.retriever.invoke(request.error_log)
    context_text = [d.page_content for d in docs]
    
    # 2. Generate (Optimized: using combine_documents_chain directly)
    # This matches the optimization done in ui.py to avoid calling Reranker twice
    raw_response = state.analyzer.qa_chain.combine_documents_chain.invoke({
        "input_documents": docs,
        "question": request.error_log
    })
    result = raw_response.get("output_text", raw_response) if isinstance(raw_response, dict) else raw_response
    
    # 3. Evaluate
    metrics = state.evaluator.evaluate_response(request.error_log, result, context_text)
    
    # 4. Save History
    # We save to SQLite
    state.history.save_analysis(
        request.error_log, 
        result, 
        metrics['faithfulness'], 
        metrics['relevancy'], 
        context_text
    )
    
    # Get ID of inserted item (simple approach for MVP)
    latest = state.history.get_history(limit=1)
    analysis_id = latest[0]['id'] if latest else None
    
    return AnalysisResponse(
        result=result,
        metrics=metrics,
        context=context_text,
        analysis_id=analysis_id
    )

@app.post("/sync")
async def sync_data(background_tasks: BackgroundTasks):
    """Triggers a full system reload to ingest new data."""
    # Run in background to not block the request
    background_tasks.add_task(initialize_system)
    return {"status": "Synchronization started in background"}

@app.get("/history")
async def get_history(limit: int = 50):
    return state.history.get_history(limit=limit)

@app.get("/stats")
async def get_stats():
    return state.history.get_stats()

@app.get("/health")
async def health_check():
    return {"status": "active", "model": "DeepSeek-R1"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
