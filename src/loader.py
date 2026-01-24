import os
import json
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader, PyPDFLoader, UnstructuredMarkdownLoader
from langchain_community.document_loaders import ConfluenceLoader
from src.config import DATA_PATH, CHUNK_SIZE, CHUNK_OVERLAP
from src.config import JIRA_URL, JIRA_API_TOKEN, JIRA_USERNAME
from src.config import CONFLUENCE_URL, CONFLUENCE_API_TOKEN, CONFLUENCE_USERNAME

class LogLoader:
    def __init__(self, data_path=DATA_PATH):
        self.data_path = data_path
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, 
            chunk_overlap=CHUNK_OVERLAP
        )

    def _process_json_file(self, file_path):
        """Processes a single JSON file and converts it into a Document."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            content_parts = []
            if "error_message" in data: content_parts.append(f"Error: {data['error_message']}")
            if "stack_trace" in data: content_parts.append(f"Stack Trace: {data['stack_trace']}")
            if "previous_fix" in data: content_parts.append(f"Solution: {data['previous_fix']}")
            
            if not content_parts:
                content_parts.append(json.dumps(data, indent=2))
            
            content = "\n".join(content_parts)
            return Document(page_content=content, metadata={"source": file_path, "type": "json", "rating": 0})
        except Exception as e:
            print(f"Error processing JSON {file_path}: {e}")
            return None

    def _load_jira(self):
        """Load Jira tickets directly using atlassian-python-api."""
        if JIRA_URL and JIRA_API_TOKEN and JIRA_USERNAME:
            try:
                from atlassian import Jira
                # Initialize Jira Client
                jira = Jira(
                    url=JIRA_URL, 
                    username=JIRA_USERNAME, 
                    password=JIRA_API_TOKEN, 
                    cloud=True
                )
                
                # JQL to fetch recent bugs
                jql = "issuetype = Bug ORDER BY created DESC"
                results = jira.jql(jql, limit=30)
                
                documents = []
                for issue in results.get("issues", []):
                    key = issue["key"]
                    fields = issue["fields"]
                    summary = fields.get("summary", "")
                    # Description can be None or complex object in some Jira versions
                    description = fields.get("description", "") or ""
                    
                    # Convert description to string if it's not
                    if not isinstance(description, str):
                        description = str(description)

                    content = f"Jira Ticket: {key}\nSummary: {summary}\nDescription: {description}"
                    
                    documents.append(Document(
                        page_content=content, 
                        metadata={
                            "source": f"{JIRA_URL}/browse/{key}", 
                            "type": "jira_bug", 
                            "rating": 0
                        }
                    ))
                
                return documents
            except Exception as e:
                print(f"Jira loading failed: {e}")
        return []

    def _load_confluence(self):
        """Placeholder for Confluence loading."""
        if CONFLUENCE_URL and CONFLUENCE_API_TOKEN and CONFLUENCE_USERNAME:
            try:
                loader = ConfluenceLoader(
                    url=CONFLUENCE_URL, 
                    api_key=CONFLUENCE_API_TOKEN, 
                    username=CONFLUENCE_USERNAME
                )
                return loader.load()
            except Exception as e:
                print(f"Confluence loading failed: {e}")
        return []

    def load(self):
        """Loads logs and error reports from multiple sources."""
        if not os.path.exists(self.data_path):
            os.makedirs(self.data_path)
            return []

        all_docs = []

        # 1. Load Local Files
        log_loader = DirectoryLoader(self.data_path, glob="./*.log", loader_cls=TextLoader)
        all_docs.extend(log_loader.load())
        
        pdf_loader = DirectoryLoader(self.data_path, glob="./*.pdf", loader_cls=PyPDFLoader)
        all_docs.extend(pdf_loader.load())

        md_loader = DirectoryLoader(self.data_path, glob="./*.md", loader_cls=UnstructuredMarkdownLoader)
        all_docs.extend(md_loader.load())

        # 2. Process JSONs manually
        for filename in os.listdir(self.data_path):
            if filename.endswith(".json"):
                file_path = os.path.join(self.data_path, filename)
                doc = self._process_json_file(file_path)
                if doc:
                    all_docs.append(doc)
        
        # 3. Load External Sources
        all_docs.extend(self._load_jira())
        all_docs.extend(self._load_confluence())

        if not all_docs:
            return []

        return self.text_splitter.split_documents(all_docs)
