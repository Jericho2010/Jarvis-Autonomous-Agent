from agent_framework import tool

try:
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    _SKLEARN_AVAILABLE = True
except ImportError:  # optional analysis extras may be missing
    np = None  # type: ignore[assignment]
    TfidfVectorizer = None  # type: ignore[assignment]
    cosine_similarity = None  # type: ignore[assignment]
    _SKLEARN_AVAILABLE = False


@tool(approval_mode="never_require")
def creative_associator(text_data):
    """Analyzes the given text data to generate creative associations and similarity scores."""
    if not _SKLEARN_AVAILABLE:
        return {
            "error": (
                "creative_associator requires scikit-learn and numpy. "
                "Install with: pip install 'jarvis[analysis]' "
                "or: pip install scikit-learn numpy"
            )
        }
    vectorizer = TfidfVectorizer()
    vectors = vectorizer.fit_transform(text_data)
    similarity_matrix = cosine_similarity(vectors)
    associations = {}
    for i in range(len(text_data)):
        for j in range(i + 1, len(text_data)):
            association = f"{text_data[i]} <-> {text_data[j]}"
            score = float(similarity_matrix[i, j])
            associations[association] = score
    return dict(sorted(associations.items(), key=lambda item: item[1], reverse=True))
