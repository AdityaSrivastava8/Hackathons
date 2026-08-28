"""
rag/retriever.py
Pure-Python TF-IDF cosine similarity retriever — zero external dependencies.
Replaces chromadb entirely so the app works on Streamlit Cloud without
onnxruntime / grpcio / numpy-version constraints.
"""
import os
import json
import math
import re
from typing import List, Dict, Any


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _tf(tokens: List[str]) -> Dict[str, float]:
    counts: Dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    total = len(tokens) or 1
    return {t: c / total for t, c in counts.items()}


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    dot = sum(a[k] * b[k] for k in keys)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class CaseRetriever:
    def __init__(self, cases_dir: str = "cases", db_path: str = "./chroma_db"):
        self.cases_dir = cases_dir
        self._docs: List[Dict[str, Any]] = []
        self._index_cases()

    def _index_cases(self) -> None:
        if not os.path.exists(self.cases_dir):
            return
        for file in os.listdir(self.cases_dir):
            if not file.endswith(".json"):
                continue
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
                self._docs.append({
                    "case_id": str(case.get("case_id", file)),
                    "text": doc_text,
                    "tf": _tf(_tokenize(doc_text)),
                    "metadata": {
                        "case_id": str(case.get("case_id", file)),
                        "title": str(case.get("title", "Unknown")),
                        "location": str(case.get("location", "Unknown")),
                        "crime_type": str(case.get("crime_type", "Unknown")),
                    },
                })
            except Exception:
                continue

    def search_similar_cases(self, suspect_query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        query_tf = _tf(_tokenize(suspect_query))
        scored = []
        for doc in self._docs:
            sim = _cosine(query_tf, doc["tf"])
            # Convert similarity to a distance-like value in [0, 2] to match
            # the shape analyzer.py already expects from the old chromadb results.
            distance = max(0.0, 1.0 - sim)
            scored.append((distance, doc))
        scored.sort(key=lambda x: x[0])
        results = []
        for distance, doc in scored[:top_k]:
            results.append({
                "case_id": doc["case_id"],
                "metadata": doc["metadata"],
                "snippet": doc["text"][:300],
                "distance": distance,
            })
        return results
