
import logging
import re

import sqlglot
from sqlglot import exp

logger = logging.getLogger(__name__)

MAX_RESULT_ROWS = 200
MAX_JOINS = 6

BLOCKED_FUNCTIONS = {
    "sleep",
    "benchmark",
    "load_file",
    "into_outfile",
    "into_dumpfile",
}


def clean_sql(sql):
    """Remove surrounding Markdown SQL code fences."""
    if not isinstance(sql, str):
        return ""

    sql = sql.strip()

    match = re.fullmatch(
        r"```(?:sql|mysql)?\s*(.*?)\s*```",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if match:
        sql = match.group(1).strip()

    return sql


def get_schema_metadata(schema):
    """Build case-insensitive table and column metadata."""
    valid_tables = {}
    valid_columns = {}

    for table_name, details in schema.items():
        normalized_table = table_name.lower()

        valid_tables[normalized_table] = table_name

        valid_columns[normalized_table] = {
            column["name"].lower()
            for column in details["columns"]
        }

    return valid_tables, valid_columns


def get_function_name(node):
    """Get a normalized SQL function name."""
    name = getattr(node, "name", "")
    return str(name).lower()


def apply_result_limit(tree):
    """
    Add a LIMIT of 200 rows if none exists.
    Preserve smaller limits and cap larger limits at 200.
    """
    limit_node = tree.args.get("limit")

    if limit_node is not None:
        limit_expression = limit_node.args.get("expression")

        if isinstance(limit_expression, exp.Literal):
            if not limit_expression.is_string:
                try:
                    current_limit = int(limit_expression.this)

                    if current_limit <= MAX_RESULT_ROWS:
                        return tree

                    limit_expression.set(
                        "this", str(MAX_RESULT_ROWS)
                    )
                    return tree

                except (TypeError, ValueError):
                    pass

    # Assign the returned tree for compatibility with sqlglot versions.
    return tree.limit(MAX_RESULT_ROWS)


def validate_sql(sql, schema):
    """
    Validate SQL against security and schema rules.

    Returns:
        (True, validated_sql) when accepted.
        (False, error_message) when rejected.
    """
    sql = clean_sql(sql)

    if not sql:
        return False, "Empty SQL query."

    # Only allow queries that start with SELECT.
    if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
        return False, "Only a single SELECT query is allowed."

    # Parse SQL using the MySQL dialect.
    try:
        statements = sqlglot.parse(sql, dialect="mysql")
    except Exception:
        return False, "Invalid SQL syntax."

    statements = [
        statement
        for statement in statements
        if statement is not None
    ]

    if len(statements) != 1:
        return False, "Exactly one SQL statement is allowed."

    tree = statements[0]

    # Reject INSERT, UPDATE, DELETE, DROP, and other non-SELECT statements.
    if not isinstance(tree, exp.Select):
        return False, "Only SELECT queries are allowed."

    # Block SELECT INTO and locking reads.
    if tree.args.get("into"):
        return False, "SELECT INTO operations are not allowed."

    if tree.args.get("locks"):
        return False, "Locking SELECT queries are not allowed."

    # Keep the current project policy against nested queries and CTEs.
    if tree.find(exp.Subquery):
        return False, "Nested subqueries are not supported."

    if tree.find(exp.CTE):
        return False, "Common table expressions are not supported."

    # Block potentially risky functions.
    for function in tree.find_all(exp.Func):
        function_name = get_function_name(function)

        if function_name in BLOCKED_FUNCTIONS:
            logger.warning(
                "Blocked risky SQL function: %s",
                function_name,
            )
            return False, (
                f"Disallowed SQL function: {function_name}"
            )

    # Restrict the number of JOIN operations.
    join_count = sum(
        1 for _ in tree.find_all(exp.Join)
    )

    if join_count > MAX_JOINS:
        return False, (
            f"Query has {join_count} joins; "
            f"maximum allowed is {MAX_JOINS}."
        )

    # Load database schema metadata.
    valid_tables, valid_columns = get_schema_metadata(schema)

    table_nodes = list(tree.find_all(exp.Table))

    if not table_nodes:
        return False, "Query must reference a database table."

    table_aliases = {}
    referenced_tables = []

    # Validate tables and build alias mappings.
    for table in table_nodes:
        table_name = table.name.lower()

        if table_name not in valid_tables:
            return False, (
                f"Invalid table detected: {table.name}"
            )

        referenced_tables.append(table_name)

        alias = table.alias

        if alias:
            table_aliases[alias.lower()] = table_name
        else:
            table_aliases[table_name] = table_name

    # Collect aliases defined in the SELECT list.
    select_aliases = {
        node.alias.lower()
        for node in tree.expressions
        if isinstance(node, exp.Alias)
    }

    # Validate column references.
    for column in tree.find_all(exp.Column):
        if column.is_star:
            continue

        column_name = column.name.lower()

        # Permit SELECT aliases used in ORDER BY.
        if (
            not column.table
            and column_name in select_aliases
            and column.find_ancestor(exp.Order)
        ):
            continue

        # Qualified column, e.g. s.student_id.
        if column.table:
            qualifier = column.table.lower()

            if qualifier not in table_aliases:
                return False, (
                    f"Invalid table alias or qualifier: "
                    f"{column.table}"
                )

            actual_table = table_aliases[qualifier]

            if column_name not in valid_columns[actual_table]:
                return False, (
                    f"Invalid column '{column.name}' "
                    f"for table '{actual_table}'."
                )

        # Unqualified column, e.g. student_id.
        else:
            matching_tables = [
                table_name
                for table_name in referenced_tables
                if column_name in valid_columns[table_name]
            ]

            if not matching_tables:
                return False, (
                    f"Invalid column detected: {column.name}"
                )

            if len(matching_tables) > 1:
                return False, (
                    f"Ambiguous column detected: {column.name}. "
                    "Specify the table alias."
                )

    # Enforce the maximum result size.
    tree = apply_result_limit(tree)

    validated_sql = tree.sql(dialect="mysql")

    logger.info("SQL query passed guardrail validation.")

    return True, validated_sql


if __name__ == "__main__":
    from app.schema import get_database_schema

    schema = get_database_schema()

    test_queries = [
        (
            "Valid SELECT",
            "SELECT * FROM student_personal_data",
        ),
        (
            "Valid limited SELECT",
            "SELECT * FROM student_personal_data LIMIT 10",
        ),
        (
            "Invalid table",
            "SELECT * FROM nonexistent_table",
        ),
        (
            "Invalid column",
            "SELECT nonexistent_column FROM student_personal_data",
        ),
        (
            "DELETE blocked",
            "DELETE FROM student_personal_data",
        ),
        (
            "Multiple statements blocked",
            "SELECT * FROM student_personal_data; "
            "DELETE FROM FEES_DETAILS",
        ),
        (
            "Risky function blocked",
            "SELECT SLEEP(10) FROM student_personal_data",
        ),
    ]

    for label, query in test_queries:
        allowed, result = validate_sql(query, schema)

        print(f"\n{label}")
        print(f"Allowed: {allowed}")
        print(f"Result: {result}")
