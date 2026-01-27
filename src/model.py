from langchain_ollama import OllamaLLM
from langchain_classic.chains import RetrievalQA
from src.config import MODEL_NAME, OLLAMA_BASE_URL
from src.prompts import PROMPT

from src.retriever import AdvancedRetrieverFactory

class BugAnalyzer:
    def __init__(self, vectorstore, chunks=None, model_name=MODEL_NAME):
        self.llm = OllamaLLM(model=model_name, base_url=OLLAMA_BASE_URL)
        
        # Configure Advanced Retriever (Hybrid + Rerank)
        retriever_factory = AdvancedRetrieverFactory(vectorstore, chunks)
        my_retriever = retriever_factory.get_retriever()
        
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=my_retriever,
            chain_type_kwargs={"prompt": PROMPT}
        )

    def analyze(self, error_log):
        """Analyzes an error log using the RAG chain."""
        return self.qa_chain.invoke(error_log)
