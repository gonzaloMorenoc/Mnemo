from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from src.config import DB_PATH, EMBEDDING_MODEL

class DatabaseInspector:
    def __init__(self, db_path=DB_PATH, model_name=EMBEDDING_MODEL):
        self.embeddings = HuggingFaceEmbeddings(model_name=model_name)
        self.vectorstore = Chroma(persist_directory=db_path, embedding_function=self.embeddings)

    def inspect(self, limit=10):
        """Displays stored document snippets and their metadata."""
        data = self.vectorstore.get()
        ids = data.get('ids', [])
        documents = data.get('documents', [])
        metadatas = data.get('metadatas', [])

        print("\n" + "="*50)
        print(f"📊 CHROMADB INSPECTOR - Total Chunks: {len(ids)}")
        print("="*50)

        if not ids:
            print("La base de datos está vacía.")
            return

        for i in range(min(limit, len(ids))):
            print(f"\n🔹 Chnk ID: {ids[i]}")
            print(f"   Fuente: {metadatas[i].get('source', 'N/A')}")
            print(f"   Tipo: {metadatas[i].get('type', 'log')}")
            print(f"   Contenido: {documents[i][:150].replace('\n', ' ')}...")
        
        print("\n" + "="*50)

if __name__ == "__main__":
    inspector = DatabaseInspector()
    inspector.inspect()
