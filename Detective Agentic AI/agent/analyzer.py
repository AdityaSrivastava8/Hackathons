from typing import Dict, Any, List
from rag.retriever import CaseRetriever


class DetectiveAgent:

    def __init__(self):
        # Create the RAG retriever when the agent is initialized.
        # app.py caches the DetectiveAgent, so this expensive setup is not
        # repeated for every suspect analysis or Streamlit rerun.
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
        # Use the actual vector similarity instead of only counting the number
        # of matched cases. This prevents different suspects with different
        # similarity strengths from receiving the same score merely because
        # they have the same number of matches.
        base_score = 15

        if matched_cases:
            similarities = []
            for case in matched_cases:
                try:
                    distance = float(case.get("distance"))
                    similarity = max(0.0, min(1.0, 1.0 - distance))
                    similarities.append(similarity)
                except (TypeError, ValueError):
                    continue

            if similarities:
                average_similarity = sum(similarities) / len(similarities)

                # Stronger RAG similarity produces a higher tendency score.
                # A small match-count bonus rewards multiple independent
                # precedents without making the score depend on count alone.
                score = base_score + (average_similarity * 70) + (len(matched_cases) * 5)
                score = min(95, max(15, round(score)))
            else:
                score = base_score
        else:
            # Fallback heuristic: analyze keyword severity if no ChromaDB
            # vector match is found.
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
