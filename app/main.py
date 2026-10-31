
from app.database import test_connection
from app.schema import get_database_schema
from app.schema_mapper import get_relevant_schema
from app.sql_translator import generate_sql
from app.guardrail import validate_sql
from app.access_control import authorize_sql, VALID_ROLES
from app.executor import execute_sql
from app.narrator import generate_natural_language_answer


def main():
    print("\n========== DATABASE CONNECTION ==========\n")

    test_connection()

    print("\n========== LOADING DATABASE SCHEMA ==========\n")

    try:
        full_schema = get_database_schema()
    except Exception as e:
        print("Could not load the database schema.")
        print("Error:", e)
        return

    print(f"Total tables discovered: {len(full_schema)}")

    # DEVELOPMENT ONLY: this is not real authentication.
    print("\n========== DEVELOPMENT ROLE SELECTION ==========\n")
    print("Available demo roles: admin, faculty, student")

    role = input("Select demo role: ").strip().lower()

    if role not in VALID_ROLES:
        print("Invalid role. Access denied.")
        return

    print(f"Demo role selected: {role}")

    question = input(
        "\nAsk a question about the student database: "
    ).strip()

    if not question:
        print("Please enter a question.")
        return

    print("\n========== SCHEMA MAPPING ==========\n")

    try:
        relevant_schema = get_relevant_schema(
            question,
            full_schema,
        )
    except Exception as e:
        print("Schema mapping failed.")
        print("Error:", e)
        return

    print("User question:")
    print(question)

    print("\nTables sent to Qwen:")
    for table_name in relevant_schema:
        print("-", table_name)

    print(
        f"\nSelected {len(relevant_schema)} "
        f"out of {len(full_schema)} tables."
    )

    print("\n========== TIER 1: SQL GENERATION ==========\n")

    try:
        generated_sql = generate_sql(question, relevant_schema)
    except Exception as e:
        print("SQL generation failed.")
        print("Error:", e)
        return

    if not generated_sql or not generated_sql.strip():
        print("Qwen returned an empty SQL query.")
        return

    print("Generated SQL:")
    print(generated_sql)

    print("\n========== TIER 2A: SQL GUARDRAIL ==========\n")

    try:
        allowed, validation_result = validate_sql(
            generated_sql,
            full_schema,
        )
    except Exception as e:
        print("Guardrail validation failed.")
        print("Error:", e)
        return

    if not allowed:
        print("STATUS: BLOCKED")
        print("Reason:", validation_result)
        return

    validated_sql = validation_result

    print("SQL safety validation passed.")

    print("\n========== TIER 2B: ACCESS CONTROL ==========\n")

    try:
        authorized, authorization_error = authorize_sql(
            validated_sql,
            role,
            full_schema,
        )
    except Exception as e:
        print("Authorization check failed.")
        print("Error:", e)
        return

    if not authorized:
        print("STATUS: ACCESS DENIED")
        print("Reason:", authorization_error)
        return

    print(f"Access granted for demo role: {role}")

    print("\nValidated and authorized SQL:")
    print(validated_sql)

    print("\n========== TIER 3A: DATABASE EXECUTION ==========\n")

    try:
        execution_result = execute_sql(validated_sql)
    except Exception as e:
        print("Database execution failed.")
        print("Error:", e)
        return

    if not execution_result["success"]:
        print("DATABASE EXECUTION FAILED")
        print("Error:", execution_result["error"])
        return

    rows = execution_result["rows"]

    print("Execution successful.")
    print(f"Rows returned: {len(rows)}")
    print("\nDatabase results:")
    print(rows)

    print("\n========== TIER 3B: NARRATOR ==========\n")

    try:
        answer = generate_natural_language_answer(
            question,
            validated_sql,
            rows,
        )
    except Exception as e:
        print("Narrator failed.")
        print("Error:", e)
        print("\nRaw database results:")
        print(rows)
        return

    print("Final Answer:")
    print(answer)


if __name__ == "__main__":
    main()
