from agent_framework import tool

@tool(approval_mode="never_require")
def metaphorical_analysis(text):
    """Attempts to analyze metaphorical language in the provided text."""
    import nltk
    from nltk.tokenize import word_tokenize
    from nltk.corpus import wordnet
    tokens = word_tokenize(text)
    metaphors = {}
    for token in tokens:
        synsets = wordnet.synsets(token)
        if len(synsets) > 1:
            interpretations = [s.definition() for s in synsets]
            metaphors[token] = interpretations
    return metaphors
