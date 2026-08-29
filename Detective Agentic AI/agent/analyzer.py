from typing import Dict, Any, List
from rag.retriever import CaseRetriever


class DetectiveAgent:

    def __init__(self):
        # Create the RAG retriever when the agent is initialized.
        self.retriever = CaseRetriever()

    def evaluate_suspect(
        self,
        name: str,
        behavior: str,
        mo_suspected: str,
        personality_notes: str
    ) -> Dict[str, Any]:

        # Build one combined query from the information supplied by the frontend.
        query_str = (
            f"Behavior: {behavior}; "
            f"Motive/MO: {mo_suspected}; "
            f"Personality: {personality_notes}"
        )

        # Search the RAG case database for the most similar historical cases.
        retrieved_cases = self.retriever.search_similar_cases(
            query_str,
            top_k=3
        )

        # CaseRetriever returns distance = 1 - cosine similarity.
        # Smaller distance means stronger similarity.
        MATCH_DISTANCE_THRESHOLD = 0.80

        matched_cases: List[Dict[str, Any]] = []
        if retrieved_cases:
            for case in retrieved_cases:
                dist = case.get("distance")
                if dist is not None and float(dist) <= MATCH_DISTANCE_THRESHOLD:
                    matched_cases.append(case)

        # Dynamic Scoring Logic
        base_score = 30

        if matched_cases:
            # Each matching historical case increases the score by 20.
            match_factor = len(matched_cases) * 20
            score = min(base_score + match_factor, 95)
        else:
            # Fallback heuristic: analyze keyword severity if no ChromaDB vector match is found
            combined_text = f"{behavior} {mo_suspected} {personality_notes}".lower()
            severe_keywords = [
                "murder", "kill", "weapon", "assault", "robbery", 
                "theft", "break-in", "crime", "stolen", "force", "threat"
            ]
            kw_matches = sum(1 for kw in severe_keywords if kw in combined_text)
            
            if kw_matches > 0:
                score = min(95, max(25, base_score + (kw_matches * 15)))
            else:
                score = 15

        # Convert the numerical score into a risk category.
        if score >= 70:
            risk_level = "HIGH RISK"
        elif score >= 40:
            risk_level = "MEDIUM RISK"
        else:
            risk_level = "LOW RISK"

        # Return the structure expected by frontend (app.py)
        return {
            "suspect_name": name,
            "tendency_score": f"{score}%",
            "risk_level": risk_level,
            "summary": (
                f"Suspect pattern aligns with {len(matched_cases)} "
                f"historical cases in the vector database."
                if matched_cases else
                f"No direct vector match in database. Risk evaluated from behavioral indicators."
            ),
            "similar_cases": matched_cases
        } 
