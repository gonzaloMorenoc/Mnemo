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
