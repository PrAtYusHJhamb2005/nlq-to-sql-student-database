
from app.fuzzy_matcher import (
    fuzzy_match_token,
    fuzzy_match_phrase,
)

vocabulary = [
    "defaulters",
    "attendance",
    "scholarship",
    "academic",
]

tests = [
    ("defaukters", "defaulters"),
    ("attendence", "attendance"),
    ("scholrship", "scholarship"),
    ("academik", "academic"),
]

for typo, expected in tests:
    match, score = fuzzy_match_token(typo, vocabulary)

    print(
        f"{typo:15} -> {match!s:15} "
        f"score={score:.1f} "
        f"pass={match == expected}"
    )

print("\nPhrase tests:")

phrase_tests = [
    (
        "count students thta have kt and are defaukters",
        "defaulters",
    ),
    (
        "show students with attendence below 75",
        "attendance",
    ),
]

for question, phrase in phrase_tests:
    print(
        f"{question!r} -> "
        f"{fuzzy_match_phrase(question, phrase)}"
    )
