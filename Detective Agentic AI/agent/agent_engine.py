"""
Detective Agent - Response Synthesis Engine

Combines AST/code-structure results and RAG results into
a readable investigation report.
"""

from typing import Any, Dict, List


def _safe_text(value: Any, default: str = "Not available") -> str:
    """
    Safely converts a value to text.

    This prevents None or unexpected values from causing
    formatting problems in the final report.
    """
    if value is None:
        return default

    text = str(value).strip()
    return text if text else default


def _get_value(
    result: Dict[str, Any],
    key: str,
    default: str = "Not available",
) -> str:
    """
    Safely retrieves a value from a result dictionary.

    Using .get() instead of result[key] prevents a KeyError
    if the AST parser or RAG system doesn't provide a field.
    """
    if not isinstance(result, dict):
        return default

    return _safe_text(result.get(key), default)


def _normalise_results(results: Any) -> List[Dict[str, Any]]:
    """
    Makes sure parser/RAG output is always handled as a list
    of dictionaries.

    This allows the application to continue working even if
    a component returns a single dictionary instead of a list,
    or returns an unexpected empty value.
    """
    if not results:
        return []

    if isinstance(results, dict):
        results = [results]

    if not isinstance(results, (list, tuple)):
        return []

    return [
        result
        for result in results
        if isinstance(result, dict)
    ]


def _deduplicate_results(
    results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Removes duplicate evidence while preserving its original order.

    This keeps the Detective Agent report cleaner when the same
    code evidence is returned more than once by a search component.
    """
    unique = []
    seen = set()

    for result in results:
        path = _get_value(result, "path", "")
        details = _get_value(result, "details", "")
        snippet = _get_value(result, "snippet", "")

        # A lightweight fingerprint is created from the available
        # evidence so identical results can be detected.
        fingerprint = (
            path.lower(),
            details.lower(),
            snippet.lower(),
        )

        if fingerprint in seen:
            continue

        seen.add(fingerprint)
        unique.append(result)

    return unique


def _find_related_files(
    ast_results: List[Dict[str, Any]],
    rag_results: List[Dict[str, Any]],
) -> List[str]:
    """
    Finds files that appear in both AST and RAG results.

    This provides a simple cross-check between structural code
    analysis and semantic retrieval.
    """
    ast_files = {
        _get_value(result, "path", "")
        for result in ast_results
        if _get_value(result, "path", "") != "Not available"
    }

    rag_files = {
        _get_value(result, "path", "")
        for result in rag_results
        if _get_value(result, "path", "") != "Not available"
    }

    return sorted(ast_files.intersection(rag_files))


def generate_agent_response(query, ast_results, rag_results):
    """
    Combines AST parser results and RAG results into the
    Detective Agent's final response.

    The function signature is intentionally kept unchanged
    so existing code calling this function continues to work.
    """

    # Convert incoming results into predictable formats before
    # processing them. This prevents malformed/empty results
    # from crashing the entire application.
    ast_results = _normalise_results(ast_results)
    rag_results = _normalise_results(rag_results)

    # Remove repeated evidence so the final report doesn't
    # contain unnecessary duplicate information.
    ast_results = _deduplicate_results(ast_results)
    rag_results = _deduplicate_results(rag_results)

    query_text = _safe_text(query, "No query provided")

    # Preserve the original behavior for a search where neither
    # the AST parser nor RAG system found anything.
    if not ast_results and not rag_results:
        return (
            "🕵️ *Detective Agent:* "
            f"I searched the codebase for *{query_text}*, "
            "but found no structural definitions or matching "
            "code evidence."
        )

    report = [
        f"🕵️ *Detective Agent Analysis for:* {query_text}\n"
    ]

    # ---------------------------------------------------------
    # AST / CODE STRUCTURE RESULTS
    # ---------------------------------------------------------

    if ast_results:
        report.append("### 🔎 Code Structure Summary")

        for result in ast_results:
            # These values are retrieved safely so that a missing
            # field doesn't terminate the whole investigation.
            result_type = _get_value(result, "type")
            details = _get_value(result, "details")
            path = _get_value(result, "path")

            report.append(
                f"- *Type:* {result_type.upper()}\n"
                f"- *Details:* {details}\n"
                f"- *File:* {path}"
            )

    # ---------------------------------------------------------
    # RAG RESULTS
    # ---------------------------------------------------------

    if rag_results:
        report.append("\n### 📚 Relevant Code Snippets")

        for result in rag_results:
            path = _get_value(result, "path")
            snippet = _get_value(result, "snippet")

            report.append(
                f"- *File:* {path}\n"
                f"- *Context:*\n"
                f"text\n{snippet}\n"
            )

    # ---------------------------------------------------------
    # AST + RAG CROSS-CHECK
    # ---------------------------------------------------------

    # A file found by both systems provides stronger evidence
    # than a file found by only one source.
    related_files = _find_related_files(
        ast_results,
        rag_results,
    )

    if related_files:
        report.append("\n### 🔗 Correlated Evidence")

        report.append(
            "The following files were identified by both "
            "code-structure analysis and RAG retrieval:"
        )

        for path in related_files:
            report.append(f"- {path}")

    # ---------------------------------------------------------
    # INVESTIGATION SUMMARY
    # ---------------------------------------------------------

    evidence_sources = []

    if ast_results:
        evidence_sources.append(
            f"{len(ast_results)} structural result(s)"
        )

    if rag_results:
        evidence_sources.append(
            f"{len(rag_results)} retrieved snippet(s)"
        )

    report.append("\n### 🧠 Investigation Summary")

    report.append(
        "The query produced "
        f"*{', '.join(evidence_sources)}*. "
        "Structural evidence identifies relevant code elements, "
        "while RAG evidence provides contextual code snippets."
    )

    # Mention whether both sources independently pointed toward
    # the same files.
    if related_files:
        report.append(
            f"\n*Evidence cross-check:* "
            f"{len(related_files)} file(s) were identified "
            "by multiple evidence sources."
        )
    else:
        report.append(
            "\n*Evidence cross-check:* "
            "No file was identified by both evidence sources."
        )

    # Return one final string, preserving the original behavior
    # expected by the frontend or calling agent component.
    return "\n\n".join(report)
