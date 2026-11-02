
import re
import requests
from collections import deque
from itertools import combinations

from rapidfuzz import fuzz

from app.semantic_matcher import (
    TABLE_DESCRIPTIONS,
    build_table_embeddings,
    find_semantic_matches,
)


TABLE_KEYWORDS = {
    "student_personal_data": [
        "student details", "student records", "student profile",
        "roll number", "roll no", "student name", "student names",
        "date of birth", "birth date", "personal details",
        "personal information", "student id", "student ids",
        "defaulter", "defaulters", "defaulter students",
        "defaulter student",
    ],
    "department": [
        "department", "departments", "branch", "branches",
        "information technology", "computer science",
        "artificial intelligence and data science", "aids",
        "extc", "chemical engineering", "it students", "it branch",
    ],
    "course": [
        "course", "courses", "subject", "subjects",
        "course code", "subject code",
    ],
    "attendance_details": [
        "attendance", "attendance percentage", "attendance rate",
        "defaulter", "defaulters", "defaulter students",
        "defaulter student", "low attendance", "attendance shortage",
        "shortage of attendance", "attendance below 75",
        "attendance below 75 percent", "attendance less than 75",
        "attendance less than 75 percent", "attendance under 75",
        "below 75 percent attendance", "less than 75 percent attendance",
    ],
    "academic_details": [
        "academic record", "academic records", "academic status",
        "subjects registered", "subjects passed", "credits earned",
        "atkt", "term work", "kt", "internal kt", "term work kt",
        "failed subjects", "having kt",
    ],
    "academic_stats": [
        "marks", "internal marks", "ia marks", "external marks",
        "total marks", "grade", "grades", "subject result",
    ],
    "cgpa_details": [
        "cgpa", "sgpa", "cumulative cgpa", "semester sgpa",
        "grade point average", "grade point averages", "grade points",
    ],
    "fees_details": [
        "fee", "fees", "pending fee", "pending fees",
        "amount pending", "amount paid", "tuition fee",
        "payment status", "unpaid fees", "outstanding fees",
        "fee dues",
    ],
    "scholarship_details": [
        "scholarship", "scholarships", "ebc", "ews", "obc",
        "pmsss", "km quota", "sc/st quota",
    ],
    "student_health": [
        "health", "blood group", "allergy", "allergies",
        "medical condition", "chronic condition", "height",
        "weight", "emergency contact",
    ],
    "extracurricular_details": [
        "extracurricular", "activity", "activities", "achievement",
        "participation", "sports", "club",
    ],
    "timetable": [
        "timetable", "class schedule", "class time",
        "room number", "day of week", "lecture schedule",
    ],
    "faculty": [
        "faculty", "professor", "teacher", "teachers",
        "instructor", "faculty member",
    ],
}


FUZZY_THRESHOLD = 85
SEMANTIC_THRESHOLD = 0.65
SEMANTIC_TOP_MARGIN = 0.08

IGNORED_FUZZY_TOKENS = {
    "count", "students", "student", "having", "that",
    "their", "with", "which", "where", "show", "find",
    "below", "above", "there", "these", "those",
}

_TABLE_EMBEDDINGS = None


def normalize_text(text):
    """Normalize text for exact and fuzzy keyword matching."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def find_lexical_matches(question, schema):
    """
    Return exact and fuzzy matches separately so the final selector
    can give exact phrases stronger evidence than fuzzy token matches.
    """

    normalized_question = normalize_text(question)
    question_tokens = normalized_question.split()
    actual_names = {name.lower(): name for name in schema}
    exact_matches = set()
    fuzzy_matches = set()
    padded_question = f" {normalized_question} "

    # Exact phrase matches are the strongest lexical signal.
    for table_key, keywords in TABLE_KEYWORDS.items():
        actual_table = actual_names.get(table_key.lower())

        if actual_table is None:
            continue

        for keyword in keywords:
            normalized_keyword = normalize_text(keyword)

            if f" {normalized_keyword} " in padded_question:
                exact_matches.add(actual_table)
                break

    # Fuzzy matching catches spelling variations.
    for table_key, keywords in TABLE_KEYWORDS.items():
        actual_table = actual_names.get(table_key.lower())

        if actual_table is None or actual_table in exact_matches:
            continue

        matched = False

        for keyword in keywords:
            keyword_tokens = normalize_text(keyword).split()

            for question_token in question_tokens:
                if (
                    len(question_token) < 5
                    or question_token in IGNORED_FUZZY_TOKENS
                ):
                    continue

                for keyword_token in keyword_tokens:
                    if len(keyword_token) < 5:
                        continue

                    if fuzz.ratio(question_token, keyword_token) >= FUZZY_THRESHOLD:
                        fuzzy_matches.add(actual_table)
                        matched = True
                        break

                if matched:
                    break

            if matched:
                break

    return exact_matches, fuzzy_matches


def find_relevant_tables(question, schema):
    """Backward-compatible helper returning all lexical matches."""
    exact_matches, fuzzy_matches = find_lexical_matches(question, schema)
    return exact_matches | fuzzy_matches


def get_semantic_matches(question, schema):
    """
    Always rank schema tables semantically for the current question.
    Table-description embeddings are cached after their first creation.
    """

    global _TABLE_EMBEDDINGS

    actual_names = {name.lower(): name for name in schema}
    descriptions = {
        actual_names[name.lower()]: description
        for name, description in TABLE_DESCRIPTIONS.items()
        if name.lower() in actual_names
    }

    if not descriptions:
        print("No semantic descriptions match the database schema.")
        return []

    if _TABLE_EMBEDDINGS is None:
        _TABLE_EMBEDDINGS = build_table_embeddings(descriptions)

    embeddings = {
        name: _TABLE_EMBEDDINGS[name]
        for name in descriptions
        if name in _TABLE_EMBEDDINGS
    }

    matches = find_semantic_matches(
        question,
        descriptions,
        embeddings,
    )

    print("\nSemantic ranking (top 5):")
    for match in matches[:5]:
        print(f"  {match['table']}: {match['score']:.4f}")

    return matches


def select_candidate_tables(exact_matches, fuzzy_matches, semantic_matches):
    """
    Combine all three signals.

    Exact matches are retained as the strongest lexical evidence.
    Fuzzy-only matches are retained when semantic ranking supports them.
    Semantic matches supplement lexical matches when they are close to
    the best semantic score and pass the minimum similarity threshold.
    """

    selected = set(exact_matches)

    if semantic_matches:
        best_score = semantic_matches[0]["score"]

        semantic_candidates = {
            match["table"]
            for match in semantic_matches
            if (
                best_score >= SEMANTIC_THRESHOLD
                and match["score"] >= best_score - SEMANTIC_TOP_MARGIN
                and match["score"] >= SEMANTIC_THRESHOLD
            )
        }

        supported_fuzzy = {
            table
            for table in fuzzy_matches
            if any(
                match["table"] == table
                and match["score"] >= SEMANTIC_THRESHOLD
                and match["score"] >= best_score - SEMANTIC_TOP_MARGIN
                for match in semantic_matches
            )
        }

        selected.update(supported_fuzzy)
        selected.update(semantic_candidates)

        rejected_fuzzy = fuzzy_matches - supported_fuzzy
        if rejected_fuzzy:
            print(
                "Fuzzy matches not supported by semantic ranking:",
                sorted(rejected_fuzzy),
            )
    else:
        # If the embedding service is unavailable, retain lexical matches
        # rather than making the entire query fail.
        selected.update(fuzzy_matches)

    print("\nMatching evidence:")
    print("  Exact:", sorted(exact_matches))
    print("  Fuzzy:", sorted(fuzzy_matches))
    print(
        "  Selected candidates:",
        sorted(selected),
    )

    return selected


def get_semantic_fallback(question, schema):
    """Compatibility wrapper returning confident semantic candidates."""
    matches = get_semantic_matches(question, schema)

    if not matches or matches[0]["score"] < SEMANTIC_THRESHOLD:
        print(
            f"No semantic candidate reached threshold "
            f"{SEMANTIC_THRESHOLD:.2f}."
        )
        return set()

    best_score = matches[0]["score"]
    return {
        match["table"]
        for match in matches
        if (
            match["score"] >= SEMANTIC_THRESHOLD
            and match["score"] >= best_score - SEMANTIC_TOP_MARGIN
        )
    }


def add_student_identity_table(question, selected_tables, schema):
    """
    Add student_personal_data when a question asks who or which
    students match records in another student-related table.
    """

    actual_names = {name.lower(): name for name in schema}
    identity_table = actual_names.get("student_personal_data")

    if identity_table is None:
        return selected_tables

    normalized_question = normalize_text(question)
    tokens = set(normalized_question.split())

    asks_who = "who" in tokens
    asks_which_students = (
        "which" in tokens
        and ("student" in tokens or "students" in tokens)
    )

    if not (asks_who or asks_which_students):
        return selected_tables

    if any(table.lower() == "faculty" for table in selected_tables):
        return selected_tables

    student_record_tables = {
        "fees_details",
        "attendance_details",
        "academic_details",
        "academic_stats",
        "cgpa_details",
        "scholarship_details",
        "student_health",
        "extracurricular_details",
    }

    selected_lower = {table.lower() for table in selected_tables}

    if selected_lower.intersection(student_record_tables):
        if identity_table not in selected_tables:
            selected_tables.add(identity_table)
            print(
                "Added student identity table because the question "
                f"asks who: {identity_table}"
            )

    return selected_tables


def build_relationship_graph(schema):
    """Build a bidirectional graph from foreign-key relationships."""

    graph = {table.lower(): set() for table in schema}

    for table_name, details in schema.items():
        current = table_name.lower()

        for fk in details.get("foreign_keys", []):
            referenced = fk["references_table"].lower()

            if referenced in graph:
                graph[current].add(referenced)
                graph[referenced].add(current)

    return graph


def shortest_path(graph, start, target):
    """Find the shortest table path using breadth-first search."""

    queue = deque([(start, [start])])
    visited = {start}

    while queue:
        current, path = queue.popleft()

        if current == target:
            return path

        for neighbour in graph.get(current, set()):
            if neighbour not in visited:
                visited.add(neighbour)
                queue.append((neighbour, path + [neighbour]))

    return []


def get_relevant_schema(question, full_schema):
    """
    Run exact, fuzzy, and semantic matching for every question,
    combine their evidence, then add identity and FK bridge tables.
    """

    exact_matches, fuzzy_matches = find_lexical_matches(
        question,
        full_schema,
    )

    try:
        semantic_matches = get_semantic_matches(question, full_schema)
    except (ValueError, KeyError, requests.RequestException) as error:
        print(f"Semantic matching failed: {error}")
        semantic_matches = []

    seed_tables = select_candidate_tables(
        exact_matches,
        fuzzy_matches,
        semantic_matches,
    )

    if not seed_tables:
        print("No reliable match; returning the full schema.")
        return full_schema

    seed_tables = add_student_identity_table(
        question,
        seed_tables,
        full_schema,
    )

    graph = build_relationship_graph(full_schema)
    selected_lower = {table.lower() for table in seed_tables}

    # Add bridge tables between every selected pair.
    for start, target in combinations(sorted(selected_lower), 2):
        path = shortest_path(graph, start, target)
        selected_lower.update(path)

    result = {
        table_name: details
        for table_name, details in full_schema.items()
        if table_name.lower() in selected_lower
    }

    print("\nRelevant schema tables:")
    for table_name in result:
        print(f"  {table_name}")

    return result
