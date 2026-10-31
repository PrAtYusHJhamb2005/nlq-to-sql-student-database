
import logging

from sqlalchemy import text

from app.database import engine
from app.schema import get_database_schema
from app.guardrail import validate_sql, MAX_RESULT_ROWS

logger = logging.getLogger(__name__)


def execute_sql(sql):
    """
    Validate SQL again before executing it.

    Returns:
        {
            "success": bool,
            "rows": list,
            "error": str | None
        }
    """
    try:
        schema = get_database_schema()
        allowed, validated_sql = validate_sql(sql, schema)

        if not allowed:
            logger.warning(
                "SQL execution blocked by guardrail: %s",
                validated_sql,
            )

            return {
                "success": False,
                "rows": [],
                "error": f"Query blocked by guardrail: {validated_sql}",
            }

        with engine.connect() as connection:
            result = connection.execute(text(validated_sql))

            rows = result.mappings().fetchmany(MAX_RESULT_ROWS)

            return {
                "success": True,
                "rows": [dict(row) for row in rows],
                "error": None,
            }

    except Exception:
        logger.exception("SQL execution failed.")

        return {
            "success": False,
            "rows": [],
            "error": "SQL execution failed. Check application logs for details.",
        }
