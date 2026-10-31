
import requests
import numpy as np


EMBEDDING_MODEL = "nomic-embed-text"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"


# Descriptions for all 13 tables in student_management_db.
TABLE_DESCRIPTIONS = {
    "ACADEMIC_DETAILS": (
        "Student academic records, semester academic status, "
        "subjects registered, subjects passed, failed subjects, "
        "ATKT, KT in internal assessments, and KT in term work. "
        "Used to find students who have passed or failed subjects "
        "and students with academic backlogs."
    ),

    "ACADEMIC_STATS": (
        "Student academic marks and subject performance, including "
        "internal assessment marks, external examination marks, "
        "total marks, grades, and subject results. Used to compare "
        "marks and find students with high or low subject scores."
    ),

    "ATTENDANCE_DETAILS": (
        "Student attendance records and attendance percentages "
        "for subjects. Used to find students with low attendance, "
        "attendance shortages, attendance below a required "
        "percentage, and attendance defaulters."
    ),

    "CGPA_DETAILS": (
        "Student CGPA and SGPA records. Contains grade point "
        "averages used to find students with the highest or "
        "lowest CGPA or SGPA and compare semester performance."
    ),

    "COURSE": (
        "College courses and subjects, including course names "
        "and course codes. Used to find subjects, identify "
        "courses, and retrieve course information."
    ),

    "DEPARTMENT": (
        "College departments and engineering branches, including "
        "IT, Computer Science, AIDS, EXTC, and Chemical Engineering. "
        "Used to find departments and identify students or courses "
        "associated with a branch."
    ),

    "EXTRACURRICULAR_DETAILS": (
        "Student extracurricular activities, participation, "
        "achievements, sports, and club activities. Used to find "
        "students who participate in activities or have received "
        "extracurricular achievements."
    ),

    "FACULTY": (
        "College faculty, professors, teachers, and instructors. "
        "Used to find faculty members and retrieve teacher "
        "information or faculty-related records."
    ),

    "FEES_DETAILS": (
        "Student college fee records, fee amounts, payments, "
        "pending fees, outstanding balances, unpaid tuition dues, "
        "and payment status. Used to find fee defaulters and "
        "students who have not paid their fees."
    ),

    "SCHOLARSHIP_DETAILS": (
        "Student scholarships, financial aid, scholarship types, "
        "and quota information, including EBC, EWS, OBC, ST/SC, "
        "KM quota, and PMSSS quota. Used to find scholarship "
        "recipients and students receiving fee concessions."
    ),

    "STUDENT_HEALTH": (
        "Student health and medical information, including blood "
        "group, allergies, medical conditions, height, weight, "
        "and emergency contact details. Used for student health "
        "and medical record queries."
    ),

    "student_personal_data": (
        "Student personal and identity details, including student "
        "names, student IDs, roll numbers, birth dates, and other "
        "personal information. Used to identify students and "
        "retrieve their personal details."
    ),

    "TIMETABLE": (
        "College timetable and class scheduling information, "
        "including lecture schedules, class times, days of the "
        "week, and room numbers. Used to find when and where "
        "classes take place."
    ),
}


# Each test has an expected table so we can measure retrieval accuracy.
TEST_CASES = [
    (
        "Which students have poor attendance?",
        "ATTENDANCE_DETAILS",
    ),
    (
        "Who has attendance below 75 percent?",
        "ATTENDANCE_DETAILS",
    ),
    (
        "Who still owes money to the college?",
        "FEES_DETAILS",
    ),
    (
        "Which students have not cleared their tuition dues?",
        "FEES_DETAILS",
    ),
    (
        "Find students with the lowest grade point average",
        "CGPA_DETAILS",
    ),
    (
        "Show students who failed subjects or have ATKT",
        "ACADEMIC_DETAILS",
    ),
    (
        "Which students scored the highest marks in exams?",
        "ACADEMIC_STATS",
    ),
    (
        "What subjects and courses are offered?",
        "COURSE",
    ),
    (
        "Show students from the Information Technology branch",
        "DEPARTMENT",
    ),
    (
        "Which students participate in sports and clubs?",
        "EXTRACURRICULAR_DETAILS",
    ),
    (
        "Find the college professors and teachers",
        "FACULTY",
    ),
    (
        "Who receives an EBC scholarship?",
        "SCHOLARSHIP_DETAILS",
    ),
    (
        "Find students with a particular blood group or allergy",
        "STUDENT_HEALTH",
    ),
    (
        "What time is the lecture and which room is it in?",
        "TIMETABLE",
    ),
    (
        "Find a student's name and roll number",
        "student_personal_data",
    ),
]


def get_embedding(text: str) -> list[float]:
    """Convert text into an embedding using Ollama."""

    response = requests.post(
        OLLAMA_EMBED_URL,
        json={
            "model": EMBEDDING_MODEL,
            "input": text,
        },
        timeout=60,
    )

    response.raise_for_status()
    data = response.json()

    embeddings = data.get("embeddings", [])

    if not embeddings:
        raise ValueError(
            f"Ollama returned no embedding for: {text}"
        )

    return embeddings[0]


def cosine_similarity(
    embedding_a: list[float],
    embedding_b: list[float],
) -> float:
    """Calculate cosine similarity between two vectors."""

    vector_a = np.array(embedding_a, dtype=float)
    vector_b = np.array(embedding_b, dtype=float)

    if vector_a.shape != vector_b.shape:
        raise ValueError("Embedding dimensions do not match.")

    norm_a = np.linalg.norm(vector_a)
    norm_b = np.linalg.norm(vector_b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(
        np.dot(vector_a, vector_b) / (norm_a * norm_b)
    )


def build_table_embeddings(
    table_descriptions: dict[str, str],
) -> dict[str, list[float]]:
    """
    Generate each table embedding once.
    Reuse these embeddings for all questions in a test run.
    """

    embeddings = {}

    for table_name, description in table_descriptions.items():
        print(f"Creating embedding: {table_name}")

        embeddings[table_name] = get_embedding(description)

    return embeddings


def find_semantic_matches(
    question: str,
    table_descriptions: dict[str, str],
    table_embeddings: dict[str, list[float]] | None = None,
) -> list[dict]:
    """
    Rank tables by semantic similarity to a question.
    """

    question_embedding = get_embedding(question)

    if table_embeddings is None:
        table_embeddings = build_table_embeddings(
            table_descriptions
        )

    results = []

    for table_name, description in table_descriptions.items():
        table_embedding = table_embeddings[table_name]

        score = cosine_similarity(
            question_embedding,
            table_embedding,
        )

        results.append({
            "table": table_name,
            "description": description,
            "score": round(score, 4),
        })

    results.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return results


def run_tests():
    """Run the full semantic retrieval test suite."""

    print("=" * 65)
    print("SEMANTIC MATCHING TESTS")
    print("=" * 65)

    print(f"\nTables: {len(TABLE_DESCRIPTIONS)}")
    print(f"Test questions: {len(TEST_CASES)}")

    # Generate the 13 table embeddings just once.
    table_embeddings = build_table_embeddings(
        TABLE_DESCRIPTIONS
    )

    passed = 0
    failed = 0
    failures = []

    for index, (question, expected_table) in enumerate(
        TEST_CASES,
        start=1,
    ):
        matches = find_semantic_matches(
            question,
            TABLE_DESCRIPTIONS,
            table_embeddings,
        )

        top_match = matches[0]
        correct_rank = next(
            (
                rank
                for rank, match in enumerate(matches, start=1)
                if match["table"] == expected_table
            ),
            None,
        )

        is_correct = top_match["table"] == expected_table

        if is_correct:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"

            failures.append({
                "question": question,
                "expected": expected_table,
                "predicted": top_match["table"],
                "expected_rank": correct_rank,
            })

        print(f"\nTest {index}: {status}")
        print(f"Question: {question}")
        print(f"Expected: {expected_table}")
        print(
            f"Top match: {top_match['table']} "
            f"(score: {top_match['score']:.4f})"
        )

        if not is_correct:
            print(f"Expected table rank: {correct_rank}")

        print("Top 3 candidates:")

        for match in matches[:3]:
            print(
                f"  {match['table']}: "
                f"{match['score']:.4f}"
            )

    total = len(TEST_CASES)
    accuracy = (passed / total * 100) if total else 0.0

    print("\n" + "=" * 65)
    print("FINAL RESULTS")
    print("=" * 65)
    print(f"Passed: {passed}/{total}")
    print(f"Failed: {failed}/{total}")
    print(f"Top-1 accuracy: {accuracy:.2f}%")

    if failures:
        print("\nQuestions needing improvement:")

        for failure in failures:
            print(f"\nQuestion: {failure['question']}")
            print(f"Expected: {failure['expected']}")
            print(f"Predicted: {failure['predicted']}")
            print(f"Expected rank: {failure['expected_rank']}")

    else:
        print("\nAll expected tables ranked first.")

    print(
        "\nNote: This tests table retrieval only, "
        "not SQL generation or query correctness."
    )


if __name__ == "__main__":
    try:
        run_tests()

    except requests.RequestException as error:
        print("\nCould not connect to Ollama.")
        print("Check that Ollama is running and the model exists.")
        print(f"Details: {error}")

    except (ValueError, KeyError) as error:
        print(f"\nSemantic matching error: {error}")
