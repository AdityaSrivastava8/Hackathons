import os
import re


# Files that are useful for codebase retrieval.
SUPPORTED_EXTENSIONS = (
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".md",
    ".json",
    ".txt",
)


def _tokenize(text):
    """Convert text into simple searchable tokens."""
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())


def build_simple_rag_index(target_dir):
    """
    Read supported codebase files and create an in-memory
    text index.

    Each document stores:
    - file path
    - complete file content
    - searchable tokens
    """

    documents = []

    if not target_dir or not os.path.isdir(target_dir):
        return documents

    for root, dirs, files in os.walk(target_dir):

        # Avoid indexing common generated/dependency directories.
        dirs[:] = [
            d for d in dirs
            if d not in {
                ".git",
                "__pycache__",
                ".venv",
                "venv",
                "node_modules",
                ".streamlit",
            }
        ]

        for file in files:

            if not file.lower().endswith(SUPPORTED_EXTENSIONS):
                continue

            file_path = os.path.join(root, file)

            try:
                with open(
                    file_path,
                    "r",
                    encoding="utf-8",
                    errors="ignore"
                ) as f:
                    content = f.read()

                if not content.strip():
                    continue

                documents.append({
                    "path": file_path,
                    "content": content,
                    "tokens": _tokenize(content),
                })

            except (OSError, UnicodeError):
                # Skip unreadable files without crashing the indexer.
                continue

    return documents


def _calculate_match_score(query_tokens, document_tokens):
    """
    Calculate a simple token-overlap score.

    This is intentionally lightweight and dependency-free.
    It is not a neural embedding model.
    """

    if not query_tokens or not document_tokens:
        return 0.0

    document_token_set = set(document_tokens)

    matched_tokens = sum(
        1
        for token in set(query_tokens)
        if token in document_token_set
    )

    unique_query_tokens = len(set(query_tokens))

    if unique_query_tokens == 0:
        return 0.0

    return matched_tokens / unique_query_tokens


def _make_snippet(content, query, window=180):
    """
    Create a useful snippet around the first matching query token.
    """

    if not content:
        return ""

    content_lower = content.lower()

    # First try the complete query.
    exact_index = content_lower.find(query.lower())

    if exact_index >= 0:
        start = max(0, exact_index - window)
        end = min(
            len(content),
            exact_index + len(query) + window
        )

        return (
            content[start:end]
            .replace("\n", " ")
            .strip()
        )

    # Otherwise find the first useful query token.
    for token in _tokenize(query):

        index = content_lower.find(token.lower())

        if index >= 0:
            start = max(0, index - window)
            end = min(
                len(content),
                index + len(token) + window
            )

            return (
                content[start:end]
                .replace("\n", " ")
                .strip()
            )

    # No direct token found.
    return content[:window * 2].replace("\n", " ").strip()


def query_rag_engine(documents, query, top_k=5):
    """
    Search indexed codebase documents using lightweight
    token matching and return the best matching files.

    This is a dependency-free retrieval layer and can be
    used as a fallback/basic RAG search.
    """

    if not documents:
        return []

    if not query or not query.strip():
        return []

    query = query.strip()
    query_tokens = _tokenize(query)

    if not query_tokens:
        return []

    scored_results = []

    for doc in documents:

        content = doc.get("content", "")
        path = doc.get("path", "")

        if not content:
            continue

        document_tokens = doc.get("tokens")

        if document_tokens is None:
            document_tokens = _tokenize(content)

        score = _calculate_match_score(
            query_tokens,
            document_tokens
        )

        # Give an exact phrase match a small ranking boost.
        if query.lower() in content.lower():
            score += 1.0

        if score > 0:
            scored_results.append({
                "path": path,
                "snippet": _make_snippet(
                    content,
                    query
                ),
                "score": round(score, 4),
            })

    # Highest-scoring documents first.
    scored_results.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return scored_results[:max(1, int(top_k))] 
