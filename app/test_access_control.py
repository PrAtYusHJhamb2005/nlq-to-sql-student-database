
import pytest

from app.access_control import authorize_sql
from app.schema import get_database_schema


@pytest.fixture(scope="module")
def schema():
    return get_database_schema()


@pytest.mark.parametrize(
    "role,table",
    [
        ("admin", "student_personal_data"),
        ("admin", "STUDENT_HEALTH"),
        ("admin", "FEES_DETAILS"),
        ("faculty", "ATTENDANCE_DETAILS"),
        ("faculty", "ACADEMIC_DETAILS"),
        ("faculty", "COURSE"),
        ("student", "COURSE"),
        ("student", "DEPARTMENT"),
        ("student", "TIMETABLE"),
    ],
)
def test_allowed_role_table_pairs(schema, role, table):
    if table not in schema:
        pytest.skip(f"Table {table} not found in database.")

    sql = f"SELECT * FROM `{table}` LIMIT 5"
    allowed, reason = authorize_sql(sql, role, schema)

    assert allowed, reason


@pytest.mark.parametrize(
    "role,table",
    [
        ("faculty", "STUDENT_HEALTH"),
        ("faculty", "FEES_DETAILS"),
        ("faculty", "SCHOLARSHIP_DETAILS"),
        ("student", "STUDENT_HEALTH"),
        ("student", "FEES_DETAILS"),
        ("student", "SCHOLARSHIP_DETAILS"),
        ("student", "student_personal_data"),
        ("student", "ACADEMIC_DETAILS"),
        ("student", "ATTENDANCE_DETAILS"),
    ],
)
def test_denied_role_table_pairs(schema, role, table):
    if table not in schema:
        pytest.skip(f"Table {table} not found in database.")

    sql = f"SELECT * FROM `{table}` LIMIT 5"
    allowed, reason = authorize_sql(sql, role, schema)

    assert not allowed


@pytest.mark.parametrize(
    "role",
    ["", "guest", "superuser", "ADMINISTRATOR", None],
)
def test_invalid_roles_rejected(schema, role):
    allowed, reason = authorize_sql(
        "SELECT * FROM COURSE",
        role,
        schema,
    )
    assert not allowed


def test_multiple_statements_rejected(schema):
    allowed, reason = authorize_sql(
        "SELECT * FROM COURSE; SELECT * FROM DEPARTMENT",
        "admin",
        schema,
    )
    assert not allowed


def test_non_select_rejected(schema):
    allowed, reason = authorize_sql(
        "DELETE FROM COURSE",
        "admin",
        schema,
    )
    assert not allowed


def test_unknown_table_rejected(schema):
    allowed, reason = authorize_sql(
        "SELECT * FROM fake_table_xyz",
        "admin",
        schema,
    )
    assert not allowed


def test_join_to_restricted_table_rejected(schema):
    if (
        "COURSE" not in schema
        or "STUDENT_HEALTH" not in schema
    ):
        pytest.skip("Required tables not found.")

    sql = """
        SELECT c.*
        FROM COURSE c
        JOIN STUDENT_HEALTH h ON 1 = 1
    """

    allowed, reason = authorize_sql(sql, "student", schema)
    assert not allowed


def test_allowed_join_between_public_tables(schema):
    if "COURSE" not in schema or "DEPARTMENT" not in schema:
        pytest.skip("Required tables not found.")

    sql = """
        SELECT c.*
        FROM COURSE c
        JOIN DEPARTMENT d ON 1 = 1
        LIMIT 5
    """

    allowed, reason = authorize_sql(sql, "student", schema)
    assert allowed, reason


def test_empty_query_rejected(schema):
    allowed, reason = authorize_sql("", "admin", schema)
    assert not allowed
