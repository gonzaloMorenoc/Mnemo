import os
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from src.config import DB_PATH, EMBEDDING_MODEL

class VectorStoreManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

    def get_vectorstore(self, chunks=None):
        """Returns a Chroma vectorstore, creating it if it doesn't exist."""
        from src.config import CHROMA_HOST, CHROMA_PORT
        
        if CHROMA_HOST:
            print(f"Connecting to remote vector database at {CHROMA_HOST}:{CHROMA_PORT}...")
            import chromadb
            client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
            if chunks:
                return Chroma.from_documents(
                    documents=chunks,
                    embedding=self.embeddings,
                    client=client,
                    collection_name="error_logs"
                )
            else:
                return Chroma(
                    client=client,
                    embedding_function=self.embeddings,
                    collection_name="error_logs"
                )

        if os.path.exists(self.db_path) and not (chunks):
            print("Loading existing vector database...")
            return Chroma(persist_directory=self.db_path, embedding_function=self.embeddings)
        
        if chunks:
            print("Creating/Updating vector database...")
            return Chroma.from_documents(
                documents=chunks,
                embedding=self.embeddings,
                persist_directory=self.db_path
            )
        
        raise ValueError("No existing DB found and no chunks provided to create one.")
    def update_feedback(self, doc_id, rating):
        """Updates the rating of a specific document in ChromaDB."""
        # Note: ChromaDB update requires the full document or just metadata
        # For simplicity in this MVP, we find the doc and update its 'rating' metadata
        try:
            # Get existing metadata
            res = self.vectorstore.get(ids=[doc_id])
            if res['metadatas']:
                new_metadata = res['metadatas'][0]
                new_metadata['rating'] = new_metadata.get('rating', 0) + rating
                self.vectorstore.update_metadata(ids=[doc_id], metadatas=[new_metadata])
                return True
        except Exception as e:
            print(f"Error updating feedback: {e}")
        return False
