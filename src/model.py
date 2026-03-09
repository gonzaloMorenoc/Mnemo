from langchain_ollama import OllamaLLM
from langchain_classic.chains import RetrievalQA
from langchain_core.documents import Document
from src.config import MODEL_NAME, OLLAMA_BASE_URL
from src.prompts import PROMPT, parse_analysis_json

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

    @staticmethod
    def _expand_to_parents(docs: list) -> list:
        """Expands retrieved child chunks to their parent context.

        With parent-child chunking, each chunk stores its parent's full text in
        metadata['parent_content']. Expanding to parents gives the LLM richer
        context while keeping retrieval precise (operating on small child chunks).
        Deduplication prevents the same parent from being passed twice.
        """
        expanded, seen = [], set()
        for doc in docs:
            parent_text = doc.metadata.get("parent_content", doc.page_content)
            if parent_text not in seen:
                seen.add(parent_text)
                expanded.append(Document(page_content=parent_text, metadata=doc.metadata))
        return expanded

    def stream(self, docs: list, question: str):
        """Streams the LLM analysis response token by token.

        Accepts already-retrieved child chunks; automatically expands them to
        parent context before building the prompt so the LLM sees more complete
        information while retrieval stayed precise.
        Yields raw string chunks as they arrive from the model.
        """
        expanded = self._expand_to_parents(docs)
        context = "\n\n---\n\n".join(doc.page_content for doc in expanded)
        formatted_prompt = PROMPT.format(context=context, question=question)
        for chunk in self.llm.stream(formatted_prompt):
            yield chunk

    def analyze(self, error_log: str) -> dict:
        """Non-streaming analysis via the full RetrievalQA chain (CLI/API use)."""
        return self.qa_chain.invoke(error_log)

    @staticmethod
    def parse_result(raw: str) -> dict | None:
        """Convenience wrapper so callers don't need to import parse_analysis_json."""
        return parse_analysis_json(raw)
