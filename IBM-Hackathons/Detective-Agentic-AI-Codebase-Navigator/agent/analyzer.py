import json
from typing import Dict, Any
from rag.retriever import CaseRetriever

class DetectiveAgent:
    def __init__(self):
        self.retriever = CaseRetriever()

    def evaluate_suspect(self, name: str, behavior: str, mo_suspected: str, personality_notes: str) -> Dict[str, Any]:
        query_str = f"Behavior: {behavior}. MO: {mo_suspected}. Personality: {personality_notes}."
        matched_cases = self.retriever.search_similar_cases(query_str, top_k=3)
        
        base_score = 30
        if matched_cases:
            match_factor = len(matched_cases) * 20
            score = min(base_score + match_factor, 95)
        else:
            score = 15

        risk_level = "HIGH RISK" if score >= 70 else "MEDIUM RISK" if score >= 40 else "LOW RISK"

        return {
            "suspect_name": name,
            "tendency_score": f"{score}%",
            "risk_level": risk_level,
            "summary": f"Suspect pattern aligns with {len(matched_cases)} historical cases in the database.",
            "similar_cases": matched_cases
        }   