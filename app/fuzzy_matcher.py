
import re
from rapidfuzz import fuzz


# Similarity thresholds: higher means stricter matching.
TOKEN_THRESHOLD = 85
PHRASE_THRESHOLD = 85

STOP_WORDS = {
    "count", "show", "find", "get", "list",
    "the", "that", "with", "having", "have",
    "has", "are", "is", "and", "for", "from",
    "who", "which", "what", "their", "below",
    "above", "less", "than", "more"
}


def normalize_text(text: str) -> str:
    """Normalize text for comparison without changing its meaning."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9_%\s]", " ", text)
    return " ".join(text.split())


def fuzzy_match_token(token: str, vocabulary: list[str],
                      threshold: int = TOKEN_THRESHOLD):
    """
    Find the closest sufficiently similar vocabulary word.

    Returns the matched word and similarity score,
    or (None, 0) when no reliable match is found.
    """
    token = normalize_text(token)

    if len(token) < 5:
        return None, 0

    candidates = [
        word for word in vocabulary
        if len(word) >= 5
    ]

    if not candidates:
        return None, 0

    match = max(
        candidates,
        key=lambda word: fuzz.ratio(token, word)
    )

    score = fuzz.ratio(token, match)

    if score >= threshold:
        return match, score

    return None, score


def fuzzy_match_phrase(question: str, phrase: str,
                       threshold: int = PHRASE_THRESHOLD) -> bool:
    """
    Check whether a phrase appears in a question,
    allowing minor spelling errors in longer words.
    """
    question = normalize_text(question)
    phrase = normalize_text(phrase)

    # Exact phrase matching is always preferred.
    if re.search(
        rf"(?<!\w){re.escape(phrase)}(?!\w)",
        question
    ):
        return True

    question_tokens = question.split()
    phrase_tokens = phrase.split()

    if not phrase_tokens:
        return False

    # Match each important phrase word to a question word.
    for target in phrase_tokens:
        if target in STOP_WORDS:
            if target not in question_tokens:
                return False
            continue

        if len(target) < 5:
            if target not in question_tokens:
                return False
            continue

        best_score = max(
            (
                fuzz.ratio(target, token)
                for token in question_tokens
                if len(token) >= 5
            ),
            default=0
        )

        if best_score < threshold:
            return False

    return True
