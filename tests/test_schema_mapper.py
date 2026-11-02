import pytest

from app import schema_mapper


# These tests exercise the schema-mapping pipeline without requiring a
# running Ollama server. Semantic results are controlled so the tests are
# deterministic; live embedding quality is tested separately.


QUESTIONS = [
    pytest.param(
        "How many students are enrolled in the college?",
        "student_personal_data",
        id="enrolled-student-count",
    ),
    pytest.param(
        "What is the total student strength?",
        "student_personal_data",
        id="total-student-strength",
    ),
    pytest.param(
        "Count students receiving an EBC scholarship.",
        "SCHOLARSHIP_DETAILS",
        id="ebc-scholarship-count",
    ),
    pytest.param(
        "How many students have attendance below 75%?",
        "ATTENDANCE_DETAILS",
        id="low-attendance-count",
    ),
    pytest.param(
        "Who hasn't cleared their college dues?",
        "FEES_DETAILS",
        id="unpaid-college-dues",
    ),
    pytest.param(
        "Find students with the lowest grade point average.",
        "CGPA_DETAILS",
        id="lowest-grade-point-average",
    ),
    pytest.param(
        "How many faculty members work in the college?",
        "FACULTY",
        id="faculty-count",
    ),
    pytest.param(
        "Show students participating in extracurricular activities.",
        "EXTRACURRICULAR_DETAILS",
        id="extracurricular-participation",
    ),
]


def make_schema():
    """Build a small schema fixture with the real project table names."""

    table_names = [
        "student_personal_data",
        "DEPARTMENT",
        "COURSE",
        "ATTENDANCE_DETAILS",
        "ACADEMIC_DETAILS",
        "ACADEMIC_STATS",
        "CGPA_DETAILS",
        "FEES_DETAILS",
        "SCHOLARSHIP_DETAILS",
        "STUDENT_HEALTH",
        "EXTRACURRICULAR_DETAILS",
        "TIMETABLE",
        "FACULTY",
    ]

    return {
        table_name: {
            "columns": [{"name": "student_id", "type": "INT"}],
            "primary_key": ["student_id"],
            "foreign_keys": [],
        }
        for table_name in table_names
    }


@pytest.fixture
def full_schema():
    return make_schema()


@pytest.mark.parametrize(("question", "expected_table"), QUESTIONS)
def test_question_maps_to_expected_table(
    question,
    expected_table,
    full_schema,
    monkeypatch,
):
    """Each of the eight example questions should retrieve its main table."""

    def fake_semantic_matches(current_question, schema):
        assert current_question == question

        # The expected table is deliberately the clear semantic winner.
        # Other tables score below the configured relevance threshold.
        return [
            {
                "table": expected_table,
                "description": "Expected table for this test question.",
                "score": 0.84,
            },
            {
                "table": "DEPARTMENT",
                "description": "Unrelated department information.",
                "score": 0.51,
            },
        ]

    monkeypatch.setattr(
        schema_mapper,
        "get_semantic_matches",
        fake_semantic_matches,
    )

    relevant_schema = schema_mapper.get_relevant_schema(
        question,
        full_schema,
    )

    assert expected_table in relevant_schema


@pytest.mark.parametrize(("question", "expected_table"), QUESTIONS)
def test_semantic_matching_runs_for_every_question(
    question,
    expected_table,
    full_schema,
    monkeypatch,
):
    """Semantic matching must run even when lexical matching finds a table."""

    calls = []

    def fake_semantic_matches(current_question, schema):
        calls.append(current_question)
        return [
            {
                "table": expected_table,
                "description": "Expected table for this test question.",
                "score": 0.84,
            }
        ]

    monkeypatch.setattr(
        schema_mapper,
        "get_semantic_matches",
        fake_semantic_matches,
    )

    schema_mapper.get_relevant_schema(question, full_schema)

    assert calls == [question]


def test_exact_match_is_retained_even_if_semantic_match_disagrees(
    full_schema,
):
    """An explicit exact phrase must not be discarded by semantic ranking."""

    selected = schema_mapper.select_candidate_tables(
        exact_matches={"ATTENDANCE_DETAILS"},
        fuzzy_matches=set(),
        semantic_matches=[
            {
                "table": "FEES_DETAILS",
                "description": "Fee information.",
                "score": 0.86,
            },
            {
                "table": "ATTENDANCE_DETAILS",
                "description": "Attendance information.",
                "score": 0.54,
            },
        ],
    )

    assert "ATTENDANCE_DETAILS" in selected


def test_semantic_matching_can_select_table_without_lexical_match():
    """A paraphrase with no keyword hit can still retrieve a table."""

    selected = schema_mapper.select_candidate_tables(
        exact_matches=set(),
        fuzzy_matches=set(),
        semantic_matches=[
            {
                "table": "student_personal_data",
                "description": "Student identity information.",
                "score": 0.82,
            },
            {
                "table": "DEPARTMENT",
                "description": "Department information.",
                "score": 0.50,
            },
        ],
    )

    assert selected == {"student_personal_data"}


def test_fuzzy_match_is_kept_when_semantics_support_it():
    """A typo-based fuzzy match should survive when semantic ranking agrees."""

    selected = schema_mapper.select_candidate_tables(
        exact_matches=set(),
        fuzzy_matches={"ATTENDANCE_DETAILS"},
        semantic_matches=[
            {
                "table": "ATTENDANCE_DETAILS",
                "description": "Attendance information.",
                "score": 0.83,
            },
            {
                "table": "FEES_DETAILS",
                "description": "Fee information.",
                "score": 0.49,
            },
        ],
    )

    assert "ATTENDANCE_DETAILS" in selected


def test_fuzzy_match_is_rejected_when_semantics_do_not_support_it():
    """A weak fuzzy hit should not be selected when semantic evidence disagrees."""

    selected = schema_mapper.select_candidate_tables(
        exact_matches=set(),
        fuzzy_matches={"ATTENDANCE_DETAILS"},
        semantic_matches=[
            {
                "table": "FEES_DETAILS",
                "description": "Fee information.",
                "score": 0.84,
            },
            {
                "table": "ATTENDANCE_DETAILS",
                "description": "Attendance information.",
                "score": 0.52,
            },
        ],
    )

    assert "ATTENDANCE_DETAILS" not in selected
    assert "FEES_DETAILS" in selected


def test_who_question_adds_student_identity_table(full_schema):
    """A 'who' question about student fees also needs student identity data."""

    selected = {"FEES_DETAILS"}

    result = schema_mapper.add_student_identity_table(
        "Who hasn't cleared their college dues?",
        selected,
        full_schema,
    )

    assert "FEES_DETAILS" in result
    assert "student_personal_data" in result


def test_count_question_does_not_automatically_add_student_identity(
    full_schema,
):
    """A count question should not add student identity data by default."""

    selected = {"SCHOLARSHIP_DETAILS"}

    result = schema_mapper.add_student_identity_table(
        "Count students receiving an EBC scholarship.",
        selected,
        full_schema,
    )

    assert result == {"SCHOLARSHIP_DETAILS"}
