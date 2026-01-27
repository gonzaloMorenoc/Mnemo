from langchain_classic.retrievers import EnsembleRetriever, ContextualCompressionRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
import warnings

# Suppress warnings for cleaner logs
warnings.filterwarnings("ignore")

class AdvancedRetrieverFactory:
    def __init__(self, vectorstore, chunks):
        self.vectorstore = vectorstore
        self.chunks = chunks

    def get_retriever(self):
        """
        Creates an advanced retriever pipeline with:
        1. Hybrid Search (Vector + BM25)
        2. Re-ranking (BGE-Reranker)
        """
        # 1. Base Semantic Retriever (Chroma)
        # Fetch more candidates to re-rank (k=10)
        semantic_retriever = self.vectorstore.as_retriever(
            search_kwargs={"k": 10}
        )

        if not self.chunks:
            print("Warning: No chunks provided for BM25. Falling back to simple vector retrieval.")
            return semantic_retriever

        # 2. Keyword Retriever (BM25)
        # Critical for specific error codes like "0x8004210B"
        bm25_retriever = BM25Retriever.from_documents(self.chunks)
        bm25_retriever.k = 10

        # 3. Hybrid Retriever (Ensemble)
        # Combining sparse (keyword) and dense (semantic) retrieval
        ensemble_retriever = EnsembleRetriever(
            retrievers=[bm25_retriever, semantic_retriever],
            weights=[0.4, 0.6]
        )

        # 4. Re-ranking (Cross-Encoder)
        # Using BGE-Reranker to reorder based on relevance
        try:
            print("Initializing BGE-Reranker (this may take a moment)...")
            # Using base model for balance between speed and performance
            model = HuggingFaceCrossEncoder(model_name="BAAI/bge-reranker-base")
            compressor = CrossEncoderReranker(model=model, top_n=5)
            
            compression_retriever = ContextualCompressionRetriever(
                base_compressor=compressor, 
                base_retriever=ensemble_retriever
            )
            return compression_retriever
        except Exception as e:
            print(f"Reranker initialization failed (using Hybrid only): {e}")
            return ensemble_retriever
