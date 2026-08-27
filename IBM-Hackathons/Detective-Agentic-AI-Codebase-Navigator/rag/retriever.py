import os
import json
import chromadb
from typing import List, Dict, Any

class CaseRetriever:
    def __init__(self, cases_dir: str = "cases", db_path: str = "./chroma_db"):
        self.cases_dir = cases_dir
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(name="criminal_cases")
        
        try:
            self._index_cases()
        except Exception as e:
            print(f"Indexing warning: {e}")

    def _index_cases(self) -> None:
        if not os.path.exists(self.cases_dir):
            return

        documents, metadatas, ids = [], [], []
        
        for file in os.listdir(self.cases_dir):
            if file.endswith(".json"):
                file_path = os.path.join(self.cases_dir, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if not content:
                            continue
                        case = json.loads(content)
                        
                        doc_text = (
                            f"Title: {case.get('title', '')}. "
                            f"Modus Operandi: {case.get('modus_operandi', '')}. "
                            f"Traits: {', '.join(case.get('common_traits', []))}. "
                            f"Personality: {case.get('personality_disorder', '')}."
                        )
                        
                        documents.append(doc_text)
                        metadatas.append({
                            "case_id": str(case.get("case_id", file)),
                            "title": str(case.get("title", "Unknown")),
                            "location": str(case.get("location", "Unknown")),
                            "crime_type": str(case.get("crime_type", "Unknown"))
                        })
                        ids.append(str(case.get("case_id", file)))
                except Exception:
                    continue

        if documents:
            self.collection.upsert(documents=documents, metadatas=metadatas, ids=ids)

    def search_similar_cases(self, suspect_query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        # Guard clause in case _init_ was bypassed by Streamlit caching
        if not hasattr(self, 'client') or self.client is None:
            self.client = chromadb.PersistentClient(path="./chroma_db")
        if not hasattr(self, 'collection') or self.collection is None:
            self.collection = self.client.get_or_create_collection(name="criminal_cases")
            
        results = self.collection.query(query_texts=[suspect_query], n_results=top_k)
        
        matches: List[Dict[str, Any]] = []
        docs_list = results.get("documents")
        ids_list = results.get("ids")
        metas_list = results.get("metadatas")
        dists_list = results.get("distances")

        if docs_list and ids_list and metas_list and docs_list[0] and ids_list[0] and metas_list[0]:
            for i in range(len(docs_list[0])):
                distance_val = dists_list[0][i] if dists_list and dists_list[0] else 0.0
                matches.append({
                    "case_id": ids_list[0][i],
                    "metadata": metas_list[0][i],
                    "snippet": docs_list[0][i],
                    "distance": distance_val
                })
        return matches