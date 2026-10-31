
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

IGNORED_FUZZY_TOKENS = {
    "count", "students", "student", "having", "that",
    "their", "with", "which", "where", "show", "find",
    "below", "above", "there", "these", "those",
}

_TABLE_EMBEDDINGS = None


def normalize_text(text):
    """Normalize text for exact and fuzzy keyword matching."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def find_relevant_tables(question, schema):
    """Identify seed tables using exact matching and RapidFuzz."""

    normalized_question = normalize_text(question)
    question_tokens = normalized_question.split()

    actual_names = {name.lower(): name for name in schema}
    selected = set()
    padded_question = f" {normalized_question} "

    # Pass 1: exact phrase matching
    for table_key, keywords in TABLE_KEYWORDS.items():
        actual_table = actual_names.get(table_key.lower())

        if actual_table is None:
            continue

        for keyword in keywords:
            normalized_keyword = normalize_text(keyword)

            if f" {normalized_keyword} " in padded_question:
                selected.add(actual_table)
                break

    # Pass 2: spelling-tolerant fuzzy matching
    for table_key, keywords in TABLE_KEYWORDS.items():
        actual_table = actual_names.get(table_key.lower())

        if actual_table is None or actual_table in selected:
            continue

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

                    score = fuzz.ratio(question_token, keyword_token)

                    if score >= FUZZY_THRESHOLD:
                        selected.add(actual_table)
                        break

                if actual_table in selected:
                    break

            if actual_table in selected:
                break

    return selected


def get_semantic_fallback(question, schema):
    """
    Find semantic candidates when exact and fuzzy matching
    have not found any tables. Return candidates above threshold.
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
        return set()

    # Create and cache table embeddings on first use.
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

    print("\nSemantic fallback candidates:")
    for match in matches[:5]:
        print(f"  {match['table']}: {match['score']:.4f}")

    selected = {
        match["table"]
        for match in matches
        if match["score"] >= SEMANTIC_THRESHOLD
    }

    if not selected:
        print(
            f"No candidates reached semantic threshold "
            f"{SEMANTIC_THRESHOLD:.2f}."
        )
    else:
        print("Semantic tables selected:", sorted(selected))

    return selected


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

    # Do not add student identity data to unrelated faculty questions.
    if "faculty" in selected_tables or "FACULTY" in selected_tables:
        return selected_tables

    # Add the identity table only if another selected table contains
    # student-related records.
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
    Select relevant tables, add student identity when appropriate,
    and include shortest foreign-key paths between selected tables.
    """

    seed_tables = find_relevant_tables(question, full_schema)

    if seed_tables:
        print("\nExact/fuzzy matching selected:")
        for table in sorted(seed_tables):
            print(f"  {table}")
    else:
        print(
            "\nExact/fuzzy matching found no tables. "
            "Trying semantic matching..."
        )

        try:
            seed_tables = get_semantic_fallback(question, full_schema)
        except (ValueError, KeyError, requests.RequestException) as error:
            print(f"Semantic matching failed: {error}")
            seed_tables = set()

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
