
import logging

import sqlglot
from sqlglot import exp

logger = logging.getLogger(__name__)

VALID_ROLES = {"admin", "faculty", "student"}

# Conservative table-level permissions for the prototype.
ROLE_TABLES = {
    "admin": {
        "ACADEMIC_DETAILS",
        "ACADEMIC_STATS",
        "ATTENDANCE_DETAILS",
        "CGPA_DETAILS",
        "COURSE",
        "DEPARTMENT",
        "EXTRACURRICULAR_DETAILS",
        "FACULTY",
        "FEES_DETAILS",
        "SCHOLARSHIP_DETAILS",
        "STUDENT_HEALTH",
        "student_personal_data",
        "TIMETABLE",
    },
    "faculty": {
        "ACADEMIC_DETAILS",
        "ACADEMIC_STATS",
        "ATTENDANCE_DETAILS",
        "CGPA_DETAILS",
        "COURSE",
        "DEPARTMENT",
        "EXTRACURRICULAR_DETAILS",
        "FACULTY",
        "TIMETABLE",
    },
    "student": {
        "COURSE",
        "DEPARTMENT",
        "TIMETABLE",
    },
}


def authorize_sql(sql, role, schema):
    """
    Check whether a role may access every table referenced in SQL.

    Returns:
        (True, None) if authorized.
        (False, reason) if denied.

    This is table-level authorization only. It does not provide
    row-level authorization or per-column permissions.
    """
    if not isinstance(role, str):
        return False, "A valid user role is required."

    role = role.strip().lower()

    if role not in VALID_ROLES:
        return False, "Unknown role. Access denied."

    if not isinstance(sql, str) or not sql.strip():
        return False, "SQL query is empty."

    try:
        statements = sqlglot.parse(sql, dialect="mysql")
    except Exception:
        return False, "Unable to parse SQL for authorization."

    statements = [
        statement
        for statement in statements
        if statement is not None
    ]

    if len(statements) != 1:
        return False, "Authorization requires exactly one SQL statement."

    tree = statements[0]

    if not isinstance(tree, exp.Select):
        return False, "Only SELECT queries can be authorized."

    allowed_tables = {
        name.lower()
        for name in ROLE_TABLES[role]
    }

    schema_tables = {
        name.lower(): name
        for name in schema
    }

    referenced_tables = list(tree.find_all(exp.Table))

    if not referenced_tables:
        return False, "Query must reference a database table."

    for table in referenced_tables:
        table_name = table.name.lower()

        if table_name not in schema_tables:
            return False, f"Unknown table: {table.name}"

        if table_name not in allowed_tables:
            logger.warning(
                "Access denied: role=%s table=%s",
                role,
                table.name,
            )
            return False, (
                f"Role '{role}' is not authorized to access "
                f"table '{table.name}'."
            )

    return True, None
