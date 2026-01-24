from langchain_ollama import OllamaLLM
from langchain.chains import RetrievalQA
from src.config import MODEL_NAME, OLLAMA_BASE_URL
from src.prompts import PROMPT

class BugAnalyzer:
    def __init__(self, vectorstore, model_name=MODEL_NAME):
        self.llm = OllamaLLM(model=model_name, base_url=OLLAMA_BASE_URL)
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=vectorstore.as_retriever(search_kwargs={"k": 3}),
            chain_type_kwargs={"prompt": PROMPT}
        )

    def analyze(self, error_log):
        """Analyzes an error log using the RAG chain."""
        return self.qa_chain.invoke(error_log)
