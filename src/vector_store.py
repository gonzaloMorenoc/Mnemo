import os
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from src.config import DB_PATH, EMBEDDING_MODEL

class VectorStoreManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
        self._vectorstore = None

    def get_vectorstore(self, chunks=None):
        """Returns a Chroma vectorstore, creating it if it doesn't exist."""
        from src.config import CHROMA_HOST, CHROMA_PORT

        if CHROMA_HOST:
            print(f"Connecting to remote vector database at {CHROMA_HOST}:{CHROMA_PORT}...")
            import chromadb
            client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
            if chunks:
                self._vectorstore = Chroma.from_documents(
                    documents=chunks,
                    embedding=self.embeddings,
                    client=client,
                    collection_name="error_logs"
                )
            else:
                self._vectorstore = Chroma(
                    client=client,
                    embedding_function=self.embeddings,
                    collection_name="error_logs"
                )
            return self._vectorstore

        if os.path.exists(self.db_path) and not chunks:
            print("Loading existing vector database...")
            self._vectorstore = Chroma(persist_directory=self.db_path, embedding_function=self.embeddings)
            return self._vectorstore

        if chunks:
            print("Creating/Updating vector database...")
            self._vectorstore = Chroma.from_documents(
                documents=chunks,
                embedding=self.embeddings,
                persist_directory=self.db_path
            )
            return self._vectorstore

        raise ValueError("No existing DB found and no chunks provided to create one.")

    def update_feedback(self, doc_id, rating):
        """Updates the rating of a specific document in ChromaDB."""
        if self._vectorstore is None:
            print("Error updating feedback: vectorstore not initialized.")
            return False
        try:
            res = self._vectorstore.get(ids=[doc_id])
            if res['metadatas']:
                new_metadata = res['metadatas'][0]
                new_metadata['rating'] = new_metadata.get('rating', 0) + rating
                self._vectorstore._collection.update(ids=[doc_id], metadatas=[new_metadata])
                return True
        except Exception as e:
            print(f"Error updating feedback: {e}")
        return False
