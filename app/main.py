
from app.database import test_connection
from app.schema import get_database_schema
from app.schema_mapper import get_relevant_schema
from app.sql_translator import generate_sql
from app.guardrail import validate_sql
from app.access_control import authorize_sql, VALID_ROLES
from app.executor import execute_sql
from app.narrator import generate_natural_language_answer


def process_question(question, role, full_schema):
    """Process one question through the existing three-tier pipeline."""

    print("\n========== SCHEMA MAPPING ==========\n")

    try:
        relevant_schema = get_relevant_schema(question, full_schema)
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

    print("\nFinal Answer:")
    print(answer)


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

    print("\n========== DEVELOPMENT ROLE SELECTION ==========\n")
    print("Available demo roles: admin, faculty, student")

    try:
        role = input("Select demo role: ").strip().lower()
    except EOFError:
        print("\nNo input received. Exiting.")
        return

    if role not in VALID_ROLES:
        print("Invalid role. Access denied.")
        return

    print(f"\nDemo role selected: {role}")

    print("\n========== CONTINUOUS QUERY SESSION ==========")
    print("You can ask multiple questions in this session.")
    print("Type 'no', 'exit' or 'quit' when asked to continue.")

    while True:
        try:
            question = input(
                "\nAsk a question about the student database: "
            ).strip()
        except EOFError:
            # The web API sends one question and closes stdin.
            # Exit cleanly instead of waiting for another question.
            print("\nInput stream closed. Ending session.")
            break

        if not question:
            print("Please enter a valid question.")
            continue

        if question.lower() in {"no", "exit", "quit"}:
            print("Ending query session.")
            break

        process_question(question, role, full_schema)

        print("\n" + "=" * 55)

        try:
            continue_choice = input(
                "\nWould you like to ask another question? (yes/no): "
            ).strip().lower()
        except EOFError:
            print("\nRequest completed. Ending session.")
            break

        if continue_choice in {"no", "n", "exit", "quit"}:
            print("Thank you! Query session ended.")
            break

        if continue_choice in {"yes", "y"}:
            continue

        print("Unrecognised response. Ending session.")
        break


if __name__ == "__main__":
    main()
