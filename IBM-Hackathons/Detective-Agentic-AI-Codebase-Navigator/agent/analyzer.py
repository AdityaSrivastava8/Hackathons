import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rag.retriever import CaseRetriever


class DetectiveAgent:
    def __init__(self):
        cases_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cases"))
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "chroma_db"))
        self.retriever = CaseRetriever(cases_dir=cases_dir, db_path=db_path)

    def evaluate_suspect(
        self,
        name: str,
        behavior: str,
        mo_suspected: str,
        personality_notes: str = ""
    ) -> dict:
        """
        Evaluates a suspect by searching for similar historical cases via RAG
        and computing a basic risk/tendency score from retrieved distances.
        """
        query = f"{behavior}. {mo_suspected}. {personality_notes}"
        similar_cases = self.retriever.search_similar_cases(query, top_k=3)

        # Compute tendency score from cosine-like distances (lower = more similar)
        if similar_cases:
            avg_distance = sum(c["distance"] for c in similar_cases) / len(similar_cases)
            # Distance is in [0, 2] range for normalised cosine; clamp to [0, 1]
            similarity = max(0.0, 1.0 - (avg_distance / 2.0))
            tendency_pct = round(similarity * 100)
        else:
            tendency_pct = 0

        # Determine risk level
        if tendency_pct >= 75:
            risk_level = "HIGH"
        elif tendency_pct >= 45:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        # Build matched cases list in the shape the frontend expects
        matched_cases = []
        for c in similar_cases:
            meta = c.get("metadata", {})
            matched_cases.append({
                "case_id": c.get("case_id", "N/A"),
                "case_title": meta.get("title", "Unknown Case"),
                "location": meta.get("location", "Unknown"),
                "summary": c.get("snippet", ""),
            })

        summary = (
            f"Suspect '{name}' profiled against {len(similar_cases)} historical precedent(s). "
            f"Tendency Score: {tendency_pct}% — Risk Level: {risk_level}. "
            f"Behavioral traits: {behavior[:200]}{'...' if len(behavior) > 200 else ''}"
        )

        return {
            "tendency_score": f"{tendency_pct}%",
            "risk_level": risk_level,
            "similar_cases": matched_cases,
            "summary": summary,
        }
