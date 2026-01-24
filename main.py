import sys
from src.loader import LogLoader
from src.vector_store import VectorStoreManager
from src.model import BugAnalyzer
from src.config import DATA_PATH

def main():
    print("--- Smart Error Debugger Initializing ---")
    
    # 1. Load and process logs
    loader = LogLoader()
    chunks = loader.load()
    
    if not chunks:
        print(f"No logs found in {DATA_PATH}. Please add .log or .json files.")
        # If we have no logs and no DB, we can't proceed with RAG properly, 
        # but for now let's just warn.
    
    # 2. Get Vector Store
    vs_manager = VectorStoreManager()
    try:
        vectorstore = vs_manager.get_vectorstore(chunks if chunks else None)
        
        # Show a quick summary of what's inside
        from src.inspector import DatabaseInspector
        inspector = DatabaseInspector()
        inspector.inspect(limit=0) # limit=0 runs only the header/total
    except Exception as e:
        print(f"Error initializing Vector Store: {e}")
        return

    # 3. Setup Analyzer
    analyzer = BugAnalyzer(vectorstore)
    
    print("\n--- IA DEBUGGING SYSTEM READY ---")
    print("Type 'salir' to exit.")
    
    while True:
        query = input("\nIntroduce error log / stack trace: ").strip()
        if not query:
            continue
        if query.lower() in ['salir', 'exit', 'quit']:
            break
        
        print("\nAnalyzing with AI...")
        try:
            response = analyzer.analyze(query)
            print("\n--- AI ANALYSIS REPORT ---")
            print(response["result"])
        except Exception as e:
            print(f"Error during analysis: {e}")

if __name__ == "__main__":
    main()
