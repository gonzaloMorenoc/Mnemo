from langchain_ollama import OllamaLLM
from langchain_classic.chains import RetrievalQA
from src.config import MODEL_NAME, OLLAMA_BASE_URL
from src.prompts import PROMPT

from src.retriever import AdvancedRetrieverFactory

_REWRITE_PROMPT = """You are a technical search assistant for a QA engineering team.
Given the following software error or test failure, extract a concise search query
(1-2 sentences) that captures the core problem for searching a knowledge base.

Rules:
- Omit specific line numbers, file paths, session IDs and temporary values
- Keep exception class names, method names and error codes
- Focus on the category of failure, not its specific instance

Error:
{error}

Optimized search query (return ONLY the query, no explanations):"""


class BugAnalyzer:
    def __init__(self, vectorstore, chunks=None, model_name=MODEL_NAME):
        self.llm = OllamaLLM(model=model_name, base_url=OLLAMA_BASE_URL)

        retriever_factory = AdvancedRetrieverFactory(vectorstore, chunks)
        my_retriever = retriever_factory.get_retriever()

        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=my_retriever,
            chain_type_kwargs={"prompt": PROMPT}
        )

    def rewrite_query(self, error_log: str) -> str:
        """Rewrites a noisy error log into a clean semantic search query.

        Stack traces contain many low-signal tokens (line numbers, file paths,
        session IDs) that hurt semantic retrieval. This step extracts the core
        failure pattern before hitting the vector store.
        """
        try:
            prompt = _REWRITE_PROMPT.format(error=error_log[:2000])
            rewritten = self.llm.invoke(prompt).strip()
            # Reject rewrites that are empty or suspiciously long (model hallucination)
            if rewritten and len(rewritten) < 300:
                return rewritten
        except Exception as e:
            print(f"Query rewrite failed, using original: {e}")
        return error_log

    def stream(self, docs: list, question: str):
        """Streams the LLM analysis response token by token.

        Accepts already-retrieved docs to avoid double-invocation of the reranker.
        Yields raw string chunks as they arrive from the model.
        """
        context = "\n\n---\n\n".join(doc.page_content for doc in docs)
        formatted_prompt = PROMPT.format(context=context, question=question)
        for chunk in self.llm.stream(formatted_prompt):
            yield chunk

    def analyze(self, error_log: str) -> dict:
        """Non-streaming analysis via the full RetrievalQA chain (CLI/API use)."""
        return self.qa_chain.invoke(error_log)
