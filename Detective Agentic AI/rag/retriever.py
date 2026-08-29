"""
rag/retriever.py

Pure-Python TF/cosine similarity retriever — zero external dependencies.

This keeps the lightweight implementation so the app can work on
Streamlit Cloud without ChromaDB / onnxruntime / grpcio / numpy
dependency problems.
"""

import os
import json
import math
import re
from typing import List, Dict, Any


# ── Text helpers ───────────────────────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    """Convert text into lowercase alphanumeric tokens."""
    return re.findall(r"[a-z0-9]+", str(text).lower())


def _tf(tokens: List[str]) -> Dict[str, float]:
    """Calculate simple term frequency for the supplied tokens."""
    counts: Dict[str, int] = {}

    for token in tokens:
        counts[token] = counts.get(token, 0) + 1

    total = len(tokens) or 1

    return {
        token: count / total
        for token, count in counts.items()
    }


def _cosine(
    a: Dict[str, float],
    b: Dict[str, float]
) -> float:
    """Calculate cosine similarity between two sparse vectors."""

    if not a or not b:
        return 0.0

    keys = set(a) & set(b)

    if not keys:
        return 0.0

    dot = sum(
        a[k] * b[k]
        for k in keys
    )

    mag_a = math.sqrt(
        sum(value * value for value in a.values())
    )

    mag_b = math.sqrt(
        sum(value * value for value in b.values())
    )

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return dot / (mag_a * mag_b)


# ── Case Retriever ────────────────────────────────────────────────────────────

class CaseRetriever:

    def __init__(
        self,
        cases_dir: str = "cases",
        db_path: str = "./chroma_db"
    ):
        """
        Initialize the case retriever.

        db_path is retained for compatibility with the previous
        implementation, but this version does not use ChromaDB.
        """

        # Make the cases directory reliable when the application
        # is launched from a different working directory.
        if os.path.isabs(cases_dir):
            self.cases_dir = cases_dir
        else:
            self.cases_dir = os.path.abspath(cases_dir)

        # Retained for compatibility with older code.
        self.db_path = db_path

        # In-memory case index.
        self._docs: List[Dict[str, Any]] = []

        self._index_cases()

    # ── Index case JSON files ─────────────────────────────────────────────────

    def _index_cases(self) -> None:
        """Load JSON case files and prepare them for searching."""

        if not os.path.isdir(self.cases_dir):
            return

        for file in os.listdir(self.cases_dir):

            if not file.lower().endswith(".json"):
                continue

            file_path = os.path.join(
                self.cases_dir,
                file
            )

            try:
                with open(
                    file_path,
                    "r",
                    encoding="utf-8"
                ) as f:
                    content = f.read().strip()

                if not content:
                    continue

                case = json.loads(content)

                if not isinstance(case, dict):
                    continue

                # ── Safely handle common_traits ──────────────────────────────
                traits = case.get("common_traits", [])

                if isinstance(traits, list):
                    traits_text = ", ".join(
                        str(item)
                        for item in traits
                    )

                elif isinstance(traits, str):
                    traits_text = traits

                else:
                    traits_text = str(traits)

                # ── Build searchable case text ───────────────────────────────
                doc_text = (
                    f"Title: {case.get('title', '')}. "
                    f"Modus Operandi: "
                    f"{case.get('modus_operandi', '')}. "
                    f"Traits: {traits_text}. "
                    f"Personality: "
                    f"{case.get('personality_disorder', '')}. "
                    f"Crime Type: "
                    f"{case.get('crime_type', '')}. "
                    f"Location: "
                    f"{case.get('location', '')}."
                )

                tokens = _tokenize(doc_text)

                # Don't index empty documents.
                if not tokens:
                    continue

                case_id = str(
                    case.get(
                        "case_id",
                        file
                    )
                )

                title = str(
                    case.get(
                        "title",
                        "Unknown"
                    )
                )

                location = str(
                    case.get(
                        "location",
                        "Unknown"
                    )
                )

                crime_type = str(
                    case.get(
                        "crime_type",
                        "Unknown"
                    )
                )

                self._docs.append(
                    {
                        "case_id": case_id,

                        "text": doc_text,

                        # Calculate TF once during indexing.
                        "tf": _tf(tokens),

                        "metadata": {
                            "case_id": case_id,

                            "title": title,

                            # Added for compatibility with the
                            # frontend/PDF report.
                            "case_title": title,

                            "location": location,

                            "crime_type": crime_type,
                        },
                    }
                )

            except (
                json.JSONDecodeError,
                OSError,
                TypeError,
                ValueError
            ):
                # One bad case file should not crash the whole app.
                continue

    # ── Search ─────────────────────────────────────────────────────────────────

    def search_similar_cases(
        self,
        suspect_query: str,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Return the most similar historical cases.

        Only cases with a similarity greater than zero are returned.
        This is important because analyzer.py uses the number of
        returned cases when calculating the tendency score.
        """

        # Empty query = no matches.
        if not suspect_query or not str(suspect_query).strip():
            return []

        # No indexed cases = no matches.
        if not self._docs:
            return []

        # Safely normalize top_k.
        try:
            top_k = max(1, int(top_k))
        except (TypeError, ValueError):
            top_k = 3

        query_tokens = _tokenize(suspect_query)

        if not query_tokens:
            return []

        query_tf = _tf(query_tokens)

        scored = []

        for doc in self._docs:

            similarity = _cosine(
                query_tf,
                doc["tf"]
            )

            # IMPORTANT FIX:
            # Do not return completely unrelated cases.
            if similarity <= 0:
                continue

            # Convert similarity to distance.
            # 0 = most similar.
            distance = max(
                0.0,
                1.0 - similarity
            )

            scored.append(
                (
                    distance,
                    similarity,
                    doc
                )
            )

        # Smallest distance = highest similarity.
        scored.sort(
            key=lambda item: item[0]
        )

        results: List[Dict[str, Any]] = []

        for distance, similarity, doc in scored[:top_k]:

            metadata = dict(
                doc["metadata"]
            )

            results.append(
                {
                    "case_id": doc["case_id"],

                    "metadata": metadata,

                    # Keep case_title directly available because
                    # the PDF/frontend can look for this key.
                    "case_title": metadata.get(
                        "case_title",
                        metadata.get(
                            "title",
                            "Unknown Case"
                        )
                    ),

                    "location": metadata.get(
                        "location",
                        "Unknown"
                    ),

                    "crime_type": metadata.get(
                        "crime_type",
                        "Unknown"
                    ),

                    "snippet": doc["text"][:300],

                    "distance": distance,

                    # Useful for debugging and future ranking.
                    "similarity": similarity,
                }
            )

        return results 
