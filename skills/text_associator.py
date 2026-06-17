from agent_framework import tool
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

@tool(approval_mode="never_require")
def creative_associator(text_data):
    """Analyzes the given text data to generate creative associations and similarity scores."""
    vectorizer = TfidfVectorizer()
    vectors = vectorizer.fit_transform(text_data)
    similarity_matrix = cosine_similarity(vectors)
    associations = {}
    for i in range(len(text_data)):
        for j in range(i+1, len(text_data)):
            association = f"{text_data[i]} <-> {text_data[j]}"
            score = float(similarity_matrix[i, j])
            associations[association] = score
    return dict(sorted(associations.items(), key=lambda item: item[1], reverse=True))
