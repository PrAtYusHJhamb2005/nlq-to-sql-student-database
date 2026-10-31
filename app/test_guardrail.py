
import pytest

from app.guardrail import (
    MAX_JOINS,
    MAX_RESULT_ROWS,
    validate_sql,
    clean_sql,
)
from app.schema import get_database_schema


@pytest.fixture(scope="module")
def schema():
    return get_database_schema()


@pytest.fixture(scope="module")
def valid_table(schema):
    """Choose a real table from the project's database."""
    assert schema, "Database schema must not be empty."
    return next(iter(schema))


@pytest.fixture(scope="module")
def valid_column(schema, valid_table):
    """Choose a real column from the selected table."""
    columns = schema[valid_table]["columns"]
    assert columns, f"{valid_table} must have columns."
    return columns[0]["name"]


# ---------------------------------------------------------
# 1. BASIC VALID QUERY TESTS
# ---------------------------------------------------------

def test_01_simple_select_allowed(schema, valid_table):
    allowed, result = validate_sql(
        f"SELECT * FROM `{valid_table}`", schema
    )
    assert allowed, result


def test_02_select_with_limit_allowed(schema, valid_table):
    allowed, result = validate_sql(
        f"SELECT * FROM `{valid_table}` LIMIT 10", schema
    )
    assert allowed, result


def test_03_select_with_where_allowed(
    schema, valid_table, valid_column
):
    allowed, result = validate_sql(
        f"SELECT * FROM `{valid_table}` "
        f"WHERE `{valid_column}` IS NOT NULL",
        schema,
    )
    assert allowed, result


def test_04_select_with_order_by_allowed(
    schema, valid_table, valid_column
):
    allowed, result = validate_sql(
        f"SELECT * FROM `{valid_table}` "
        f"ORDER BY `{valid_column}`",
        schema,
    )
    assert allowed, result


def test_05_select_with_count_allowed(schema, valid_table):
    allowed, result = validate_sql(
        f"SELECT COUNT(*) FROM `{valid_table}`", schema
    )
    assert allowed, result


def test_06_select_with_distinct_allowed(
    schema, valid_table, valid_column
):
    allowed, result = validate_sql(
        f"SELECT DISTINCT `{valid_column}` "
        f"FROM `{valid_table}`",
        schema,
    )
    assert allowed, result


# ---------------------------------------------------------
# 2. EMPTY AND INVALID INPUT TESTS
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        None,
        123,
        "not a SQL query",
        "SELECT",
        "SELECT * FROM",
        "SELEC * FROM student_personal_data",
    ],
)
def test_07_invalid_or_empty_input_rejected(schema, query):
    allowed, result = validate_sql(query, schema)
    assert not allowed


def test_08_markdown_sql_fence_cleaned(schema, valid_table):
    query = f"```sql\nSELECT * FROM `{valid_table}`\n```"
    allowed, result = validate_sql(query, schema)
    assert allowed, result


# ---------------------------------------------------------
# 3. DESTRUCTIVE COMMANDS MUST BE REJECTED
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM student_personal_data",
        "DROP TABLE student_personal_data",
        "UPDATE FEES_DETAILS SET amount_pending = 0",
        "INSERT INTO student_personal_data VALUES (1)",
        "TRUNCATE TABLE student_personal_data",
        "ALTER TABLE student_personal_data ADD COLUMN test_col INT",
        "CREATE TABLE test_table (id INT)",
        "REPLACE INTO student_personal_data VALUES (1)",
    ],
)
def test_09_destructive_commands_rejected(schema, query):
    allowed, result = validate_sql(query, schema)
    assert not allowed


# ---------------------------------------------------------
# 4. MULTIPLE STATEMENTS AND INJECTION-STYLE INPUTS
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        (
            "SELECT * FROM student_personal_data; "
            "DELETE FROM FEES_DETAILS"
        ),
        (
            "SELECT * FROM student_personal_data; "
            "DROP TABLE FEES_DETAILS"
        ),
        (
            "SELECT * FROM student_personal_data; "
            "UPDATE FEES_DETAILS SET amount_pending = 0"
        ),
        (
            "SELECT * FROM student_personal_data; "
            "INSERT INTO FEES_DETAILS VALUES (1)"
        ),
    ],
)
def test_10_multiple_statements_rejected(schema, query):
    allowed, result = validate_sql(query, schema)
    assert not allowed


# ---------------------------------------------------------
# 5. TABLE AND COLUMN VALIDATION
# ---------------------------------------------------------

def test_11_unknown_table_rejected(schema):
    allowed, result = validate_sql(
        "SELECT * FROM definitely_nonexistent_table_xyz",
        schema,
    )
    assert not allowed


def test_12_unknown_column_rejected(schema):
    allowed, result = validate_sql(
        "SELECT definitely_nonexistent_column_xyz "
        "FROM student_personal_data",
        schema,
    )
    assert not allowed


def test_13_unknown_alias_rejected(schema):
    allowed, result = validate_sql(
        "SELECT wrong_alias.student_id "
        "FROM student_personal_data sp",
        schema,
    )
    assert not allowed


def test_14_unknown_qualified_column_rejected(schema):
    allowed, result = validate_sql(
        "SELECT sp.definitely_fake_column "
        "FROM student_personal_data sp",
        schema,
    )
    assert not allowed


def test_15_query_without_table_rejected(schema):
    allowed, result = validate_sql("SELECT 1", schema)
    assert not allowed


# ---------------------------------------------------------
# 6. RISKY FUNCTION TESTS
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "function",
    [
        "SLEEP(10)",
        "BENCHMARK(1000000, MD5('test'))",
        "LOAD_FILE('/etc/passwd')",
    ],
)
def test_16_risky_functions_rejected(
    schema, function
):
    query = (
        "SELECT "
        + function
        + " FROM student_personal_data"
    )
    allowed, result = validate_sql(query, schema)
    assert not allowed


# ---------------------------------------------------------
# 7. QUERY COMPLEXITY TESTS
# ---------------------------------------------------------

def test_17_join_limit_boundary_allowed(schema):
    """Exactly MAX_JOINS joins should pass the join-count rule."""
    query = """
        SELECT sp.student_id
        FROM student_personal_data sp
        JOIN FEES_DETAILS f1 ON sp.student_id = f1.student_id
        JOIN FEES_DETAILS f2 ON sp.student_id = f2.student_id
        JOIN FEES_DETAILS f3 ON sp.student_id = f3.student_id
        JOIN FEES_DETAILS f4 ON sp.student_id = f4.student_id
        JOIN FEES_DETAILS f5 ON sp.student_id = f5.student_id
        JOIN FEES_DETAILS f6 ON sp.student_id = f6.student_id
    """

    if MAX_JOINS != 6:
        pytest.skip("This boundary test assumes MAX_JOINS is 6.")

    allowed, result = validate_sql(query, schema)
    assert allowed, result


def test_18_too_many_joins_rejected(schema):
    query = """
        SELECT sp.student_id
        FROM student_personal_data sp
        JOIN FEES_DETAILS f1 ON sp.student_id = f1.student_id
        JOIN FEES_DETAILS f2 ON sp.student_id = f2.student_id
        JOIN FEES_DETAILS f3 ON sp.student_id = f3.student_id
        JOIN FEES_DETAILS f4 ON sp.student_id = f4.student_id
        JOIN FEES_DETAILS f5 ON sp.student_id = f5.student_id
        JOIN FEES_DETAILS f6 ON sp.student_id = f6.student_id
        JOIN FEES_DETAILS f7 ON sp.student_id = f7.student_id
    """

    allowed, result = validate_sql(query, schema)
    assert not allowed
    assert "join" in result.lower()


# ---------------------------------------------------------
# 8. SUBQUERIES, CTEs, AND LOCKING
# ---------------------------------------------------------

def test_19_subquery_rejected(schema):
    query = """
        SELECT *
        FROM student_personal_data
        WHERE student_id IN (
            SELECT student_id FROM FEES_DETAILS
        )
    """
    allowed, result = validate_sql(query, schema)
    assert not allowed


def test_20_cte_rejected(schema):
    query = """
        WITH student_list AS (
            SELECT * FROM student_personal_data
        )
        SELECT * FROM student_list
    """
    allowed, result = validate_sql(query, schema)
    assert not allowed


def test_21_for_update_rejected(schema):
    allowed, result = validate_sql(
        "SELECT * FROM student_personal_data FOR UPDATE",
        schema,
    )
    assert not allowed


# ---------------------------------------------------------
# 9. RESULT LIMIT TESTS
# ---------------------------------------------------------

def test_22_missing_limit_gets_default_limit(
    schema, valid_table
):
    allowed, result = validate_sql(
        f"SELECT * FROM `{valid_table}`", schema
    )
    assert allowed, result
    assert f"LIMIT {MAX_RESULT_ROWS}" in result.upper()


def test_23_small_limit_preserved(schema, valid_table):
    allowed, result = validate_sql(
        f"SELECT * FROM `{valid_table}` LIMIT 10",
        schema,
    )
    assert allowed, result
    assert "LIMIT 10" in result.upper()


def test_24_large_limit_capped(schema, valid_table):
    allowed, result = validate_sql(
        f"SELECT * FROM `{valid_table}` LIMIT 10000",
        schema,
    )
    assert allowed, result
    assert f"LIMIT {MAX_RESULT_ROWS}" in result.upper()


def test_25_limit_equal_to_max_preserved(
    schema, valid_table
):
    allowed, result = validate_sql(
        f"SELECT * FROM `{valid_table}` "
        f"LIMIT {MAX_RESULT_ROWS}",
        schema,
    )
    assert allowed, result
    assert f"LIMIT {MAX_RESULT_ROWS}" in result.upper()


def test_26_zero_limit_preserved(schema, valid_table):
    allowed, result = validate_sql(
        f"SELECT * FROM `{valid_table}` LIMIT 0",
        schema,
    )
    assert allowed, result
    assert "LIMIT 0" in result.upper()


# ---------------------------------------------------------
# 10. CLEANING AND CASE HANDLING
# ---------------------------------------------------------

def test_27_clean_sql_removes_sql_fence():
    assert clean_sql(
        "```sql\nSELECT 1\n```"
    ) == "SELECT 1"


def test_28_clean_sql_removes_mysql_fence():
    assert clean_sql(
        "```mysql\nSELECT 1\n```"
    ) == "SELECT 1"


def test_29_clean_sql_handles_none():
    assert clean_sql(None) == ""


def test_30_keyword_case_handling(schema, valid_table):
    allowed, result = validate_sql(
        f"select * from `{valid_table}`",
        schema,
    )
    assert allowed, result


# ---------------------------------------------------------
# 11. REAL DATABASE SCHEMA INTEGRITY
# ---------------------------------------------------------

def test_31_database_schema_is_not_empty(schema):
    assert len(schema) > 0


def test_32_schema_tables_have_columns(schema):
    for table_name, details in schema.items():
        assert "columns" in details, table_name
        assert len(details["columns"]) > 0, table_name


def test_33_real_table_and_column_are_accepted(
    schema, valid_table, valid_column
):
    query = (
        f"SELECT `{valid_column}` "
        f"FROM `{valid_table}`"
    )

    allowed, result = validate_sql(query, schema)
    assert allowed, result


# ---------------------------------------------------------
# 12. JOIN VALIDATION
# ---------------------------------------------------------

def test_34_valid_student_fees_join_allowed(schema):
    if (
        "student_personal_data" not in schema
        or "FEES_DETAILS" not in schema
    ):
        pytest.skip("Expected student and fees tables not found.")

    student_columns = {
        c["name"].lower()
        for c in schema["student_personal_data"]["columns"]
    }
    fees_columns = {
        c["name"].lower()
        for c in schema["FEES_DETAILS"]["columns"]
    }

    if "student_id" not in student_columns or "student_id" not in fees_columns:
        pytest.skip("student_id missing from one of the tables.")

    query = """
        SELECT sp.student_id
        FROM student_personal_data sp
        JOIN FEES_DETAILS f
          ON sp.student_id = f.student_id
        LIMIT 10
    """

    allowed, result = validate_sql(query, schema)
    assert allowed, result


def test_35_invalid_join_column_rejected(schema):
    query = """
        SELECT sp.student_id
        FROM student_personal_data sp
        JOIN FEES_DETAILS f
          ON sp.fake_id = f.fake_id
    """

    allowed, result = validate_sql(query, schema)
    assert not allowed


# ---------------------------------------------------------
# 13. QUERY SHAPE AND EDGE CASES
# ---------------------------------------------------------

def test_36_union_query_rejected_by_current_policy(schema):
    query = """
        SELECT student_id FROM student_personal_data
        UNION
        SELECT student_id FROM FEES_DETAILS
    """

    allowed, result = validate_sql(query, schema)
    assert not allowed


def test_37_select_into_rejected(schema):
    allowed, result = validate_sql(
        "SELECT * INTO new_table FROM student_personal_data",
        schema,
    )
    assert not allowed


def test_38_unknown_table_with_alias_rejected(schema):
    allowed, result = validate_sql(
        "SELECT x.student_id FROM fake_students x",
        schema,
    )
    assert not allowed


def test_39_invalid_sql_does_not_return_success(schema):
    allowed, result = validate_sql(
        "SELECT FROM WHERE",
        schema,
    )
    assert not allowed


def test_40_valid_query_returns_sql_string(
    schema, valid_table
):
    allowed, result = validate_sql(
        f"SELECT * FROM `{valid_table}`",
        schema,
    )
    assert allowed
    assert isinstance(result, str)
    assert result.strip()


# ---------------------------------------------------------
# 14. ADDITIONAL POLICY REGRESSION TESTS
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        "DROP DATABASE student_management_db",
        "GRANT ALL PRIVILEGES ON *.* TO 'test'@'localhost'",
        "REVOKE ALL PRIVILEGES ON *.* FROM 'test'@'localhost'",
        "CALL some_procedure()",
        "EXECUTE some_statement",
    ],
)
def test_41_other_non_select_commands_rejected(schema, query):
    allowed, result = validate_sql(query, schema)
    assert not allowed


def test_42_unknown_column_does_not_pass(schema):
    query = (
        "SELECT totally_fake_field_123 "
        "FROM student_personal_data"
    )
    allowed, result = validate_sql(query, schema)
    assert not allowed


def test_43_existing_lower_limit_remains_lower(schema):
    query = "SELECT * FROM student_personal_data LIMIT 5"

    allowed, result = validate_sql(query, schema)

    assert allowed, result
    assert "LIMIT 5" in result.upper()


def test_44_null_input_is_rejected(schema):
    allowed, result = validate_sql(None, schema)
    assert not allowed


def test_45_whitespace_input_is_rejected(schema):
    allowed, result = validate_sql("     ", schema)
    assert not allowed
