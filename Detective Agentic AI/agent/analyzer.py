import json
from typing import Dict, Any

from rag.retriever import CaseRetriever


class DetectiveAgent:

    def _init_(self):
        # Creates the RAG retriever that will search the historical
        # case database for cases similar to the current investigation.
        self.retriever = CaseRetriever()

    def evaluate_suspect(
        self,
        name: str,
        behavior: str,
        motive_suspected: str,
        personality_notes: str
    ) -> Dict[str, Any]:

        # Combine the available information about the suspect into
        # one search query for the RAG system.
        query_str = (
            f"Behavior: {behavior}; "
            f"Motive: {motive_suspected}; "
            f"Personality: {personality_notes}"
        )

        # Search the case database for the 3 most similar historical
        # cases. The quality of this step depends on CaseRetriever.
        matched_cases = self.retriever.search_similar_cases(
            query_str,
            top_k=3
        )

        # Start with a base tendency score.
        base_score = 30

        if matched_cases:

            # Each matching historical case increases the score by 20.
            # This provides a simple heuristic based on similar cases.
            match_factor = len(matched_cases) * 20

            # Keep the score capped at 95 so that it never reaches 100.
            score = min(base_score + match_factor, 95)

        else:

            # If no similar historical cases are found, use a lower
            # default score instead of treating the suspect as high risk.
            score = 15

        # Convert the numerical score into a simple risk category.
        if score >= 70:
            risk_level = "HIGH RISK"
        elif score >= 40:
            risk_level = "MEDIUM RISK"
        else:
            risk_level = "LOW RISK"

        # Return the investigation result as a dictionary so that
        # other components of the application can use the information.
        return {
            "suspect_name": name,
            "tendency_score": f"{score}%",
            "risk_level": risk_level,

            # Explain why the score was produced.
            "summary": (
                f"Suspect pattern aligns with "
                f"{len(matched_cases)} historical cases in the database."
            ),

            # Keep the actual retrieved cases available for further
            # analysis or display by the frontend/agent.
            "similar_cases": matched_cases
        }
