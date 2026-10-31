import pytest
import sqlglot
from sqlglot import exp

from app.schema import get_database_schema
from app.schema_mapper import get_relevant_schema
from app.sql_translator import generate_sql, extract_sql


@pytest.fixture(scope="module")
def schema():
    """Load the actual database schema once for this test module."""
    return get_database_schema()


# 30 natural-language questions to test schema mapping and SQL generation.
QUESTIONS = [
    "Which students receive an EBC scholarship?",
    "Who still owes money to the college?",
    "Which students have KT and attendance below 75%?",
    "Show students with attendance below 75% in IT.",
    "Which students have unpaid fees and receive EBC scholarships?",
    "Show student names and their current semester.",
    "Count students in each department.",
    "List courses offered by the Information Technology department.",
    "Which students are in semester 6?",
    "Which students have pending fees greater than 10000?",
    "List students whose college fees are fully paid.",
    "Which scholarship applications are pending approval?",
    "Count scholarship records by eligibility category.",
    "Show students whose attendance is below 60%.",
    "Show attendance percentages by branch and semester.",
    "Show academic records for semester 5.",
    "List students with KT or ATKT.",
    "Show semester SGPA and cumulative CGPA for students.",
    "Calculate average attendance for each branch.",
    "Count attendance records for each branch.",
    "List faculty names and their initials.",
    "Show the timetable for semester 6.",
    "List extracurricular activities and participation levels.",
    "Count scholarship records by approval status.",
    "Calculate total pending fees for each academic year.",
    "Which students receive an OBC scholarship?",
    "List courses available in semester 6.",
    "Count academic records for each academic status.",
    "Count student records by health status.",
    "List course names and their credit values.",
]


@pytest.mark.parametrize(
    "question",
    QUESTIONS,
    ids=[f"Q{i:02d}" for i in range(1, len(QUESTIONS) + 1)],
)
def test_sql_generation(question, schema):
    """
    Test the schema mapper and SQL translator.

    For every natural-language question:
    1. Select a relevant subset of the live schema.
    2. Ask Qwen to generate SQL.
    3. Parse the result using SQLGlot's MySQL dialect.
    4. Check that exactly one SELECT statement was generated.
    """
    relevant_schema = get_relevant_schema(question, schema)

    assert isinstance(relevant_schema, dict), (
        f"Schema mapper did not return a dictionary for: {question}"
    )
    assert relevant_schema, (
        f"Schema mapper returned no relevant tables for: {question}"
    )

    sql = generate_sql(question, relevant_schema)

    assert isinstance(sql, str) and sql.strip(), (
        f"SQL generation returned empty output for: {question}"
    )

    statements = [
        statement
        for statement in sqlglot.parse(sql, read="mysql")
        if statement is not None
    ]

    assert len(statements) == 1, (
        f"Expected exactly one SQL statement for: {question}\n"
        f"Generated SQL:\n{sql}"
    )

    assert isinstance(statements[0], exp.Select), (
        f"Expected a SELECT statement for: {question}\n"
        f"Generated SQL:\n{sql}"
    )


# Verify that destructive SQL is not accepted by the SQL extractor.

@pytest.mark.parametrize("unsafe_sql", [
    "DELETE FROM student_personal_data",
    "DROP TABLE student_personal_data",
    "UPDATE FEES_DETAILS SET amount_pending = 0",
])
def test_extract_sql_rejects_non_select_sql(unsafe_sql):
    with pytest.raises(ValueError):
        extract_sql(unsafe_sql)


def test_extract_sql_rejects_multiple_statements():
    sql = (
        "SELECT * FROM student_personal_data; "
        "DELETE FROM FEES_DETAILS"
    )

    # A SELECT must not be extracted from a response that also
    # contains a destructive statement.
    with pytest.raises(ValueError):
        extract_sql(sql)
