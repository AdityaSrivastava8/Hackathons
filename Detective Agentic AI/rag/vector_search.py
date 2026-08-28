import os

def build_simple_rag_index(target_dir):
    """Reads codebase files and creates a basic in-memory text index."""
    documents = []
    for root, _, files in os.walk(target_dir):
        for file in files:
            if file.endswith(('.py', '.md', '.json', '.txt')):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        documents.append({"path": file_path, "content": content})
                except Exception:
                    continue
    return documents

def query_rag_engine(documents, query):
    """Searches through the content of indexed codebase files."""
    results = []
    query_lower = query.lower()
    for doc in documents:
        if query_lower in doc["content"].lower():
            # Find snippet around query match
            content_lower = doc["content"].lower()
            idx = content_lower.find(query_lower)
            start = max(0, idx - 50)
            end = min(len(doc["content"]), idx + 150)
            snippet = doc["content"][start:end].replace('\n', ' ')
            results.append({"path": doc["path"], "snippet": snippet})
    return results