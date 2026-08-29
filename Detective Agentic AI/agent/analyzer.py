import json
from typing import Dict, Any

from rag.retriever import CaseRetriever


class DetectiveAgent:

    def _init_(self):
        # FIX: The constructor must use Python's special _init_ method.
        # This creates the RAG retriever when DetectiveAgent is initialized.
        self.retriever = CaseRetriever()

    def evaluate_suspect(
        self,
        name: str,
        behavior: str,
        mo_suspected: str,
        personality_notes: str
    ) -> Dict[str, Any]:

        # Build one combined query from the information supplied
        # by the frontend.
        query_str = (
            f"Behavior: {behavior}; "
            f"Motive/MO: {mo_suspected}; "
            f"Personality: {personality_notes}"
        )

        # Search the RAG case database for the most similar
        # historical cases.
        matched_cases = self.retriever.search_similar_cases(
            query_str,
            top_k=3
        )

        # Start with the existing base tendency score.
        base_score = 30

        if matched_cases:

            # Each matching historical case increases the score by 20.
            # This preserves the original scoring logic.
            match_factor = len(matched_cases) * 20

            # Keep the maximum score at 95%.
            score = min(base_score + match_factor, 95)

        else:

            # No historical match means a lower default score.
            score = 15

        # Convert the numerical score into a risk category.
        if score >= 70:
            risk_level = "HIGH RISK"
        elif score >= 40:
            risk_level = "MEDIUM RISK"
        else:
            risk_level = "LOW RISK"

        # Return the result in the structure expected by
        # the frontend.
        return {
            "suspect_name": name,
            "tendency_score": f"{score}%",
            "risk_level": risk_level,

            # Explain the basis of the current score.
            "summary": (
                f"Suspect pattern aligns with "
                f"{len(matched_cases)} historical cases in the database."
            ),

            # Keep the retrieved cases available to the frontend
            # for display and PDF report generation.
            "similar_cases": matched_cases
        } 
