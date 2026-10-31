
import json
import re

import ollama
import sqlglot
from sqlglot import exp


KT_STATUSES = (
    "KT",
    "ATKT",
    "Internal KT",
    "Term Work KT",
)


def extract_sql(model_output):
    """Extract exactly one valid MySQL SELECT query from Qwen's response."""

    if not isinstance(model_output, str) or not model_output.strip():
        raise ValueError("Qwen returned an empty response.")

    model_output = re.sub(
        r"<think>.*?</think>",
        "",
        model_output,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()

    def parse_statements(candidate):
        """Parse SQL and return all non-empty statements."""
        return [
            statement
            for statement in sqlglot.parse(candidate, dialect="mysql")
            if statement is not None
        ]

    def is_single_select(candidate):
        """Return True only when there is exactly one SELECT statement."""
        try:
            statements = parse_statements(candidate)
            return (
                len(statements) == 1
                and isinstance(statements[0], exp.Select)
            )
        except Exception:
            return False

    # Reject multiple SQL statements in a raw SQL response.
    # Do not silently extract a SELECT from a destructive SQL sequence.
    try:
        parsed_statements = parse_statements(model_output)
        if len(parsed_statements) > 1:
            raise ValueError("Qwen returned multiple SQL statements.")
    except ValueError:
        raise
    except Exception:
        # The response may contain explanatory text or a SQL code block.
        pass

    # Prefer a valid query inside a SQL code block.
    code_blocks = re.findall(
        r"```(?:sql|mysql)?\s*(.*?)```",
        model_output,
        flags=re.IGNORECASE | re.DOTALL,
    )

    valid_blocks = [
        block.strip()
        for block in code_blocks
        if is_single_select(block.strip())
    ]

    if len(valid_blocks) == 1:
        return valid_blocks[0]

    if len(valid_blocks) > 1:
        raise ValueError(
            "Qwen returned multiple valid SQL code blocks."
        )

    # Accept a response that is already a single SELECT.
    if is_single_select(model_output):
        return model_output

    # Otherwise, look for a SELECT embedded in explanatory text.
    # Before accepting an extracted query, reject responses containing
    # additional SQL statements separated by semicolons.
    candidates = []

    for match in re.finditer(
        r"\bSELECT\b",
        model_output,
        flags=re.IGNORECASE,
    ):
        start = match.start()
        remaining_text = model_output[start:]

        # A semicolon followed by another SQL command means the response
        # must not be accepted by extracting only the first SELECT.
        if re.search(
            r";\s*(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE)\b",
            remaining_text,
            flags=re.IGNORECASE,
        ):
            raise ValueError(
                "Qwen's response contains multiple SQL statements."
            )

        boundaries = {len(model_output)}

        for end_match in re.finditer(r";|\n", remaining_text):
            if end_match.group() == ";":
                end = start + end_match.end()
            else:
                end = start + end_match.start()

            boundaries.add(end)

        for end in boundaries:
            candidate = model_output[start:end].strip()

            if candidate and is_single_select(candidate):
                candidates.append(candidate)

    if candidates:
        return max(candidates, key=len)

    raise ValueError(
        "Could not extract a valid SELECT query from Qwen's response.\n"
        "Raw response preview:\n"
        + model_output[:500]
    )


def validate_question_requirements(question, sql, schema):
    """
    Validate required concepts for the known KT + defaulter rule.

    This is a targeted business-rule check, not a complete proof
    of SQL semantic correctness.
    """

    normalized_question = question.lower()
    normalized_sql = sql.lower()

    asks_about_kt = bool(
        re.search(r"\bkt\b|\batkt\b", normalized_question)
    )

    asks_about_defaulters = bool(
        re.search(r"\bdefaulters?\b", normalized_question)
    )

    if not (asks_about_kt and asks_about_defaulters):
        return

    schema_names = {
        table_name.lower()
        for table_name in schema
    }

    required_tables = {
        "academic_details",
        "attendance_details",
    }

    missing_tables = required_tables - schema_names

    if missing_tables:
        raise ValueError(
            "Cannot answer the KT + defaulter question because "
            "the supplied schema is missing required tables: "
            + ", ".join(sorted(missing_tables))
        )

    for table_name in required_tables:
        if not re.search(
            rf"\b{re.escape(table_name)}\b",
            normalized_sql,
        ):
            raise ValueError(
                f"Generated SQL is missing required table: {table_name}"
            )

    required_columns = (
        "academic_status",
        "attendance_percentage",
        "academic_year",
        "semester",
    )

    for column_name in required_columns:
        if not re.search(
            rf"\b{re.escape(column_name)}\b",
            normalized_sql,
        ):
            raise ValueError(
                "Generated SQL is missing required column: "
                + column_name
            )

    if not re.search(
        r"\battendance_percentage\b\s*<\s*75(?:\.0+)?\b",
        normalized_sql,
    ):
        raise ValueError(
            "Generated SQL must enforce attendance below 75%."
        )

    for status in KT_STATUSES:
        if not re.search(
            r"['\"]" + re.escape(status.lower()) + r"['\"]",
            normalized_sql,
        ):
            raise ValueError(
                "Generated SQL is missing a required "
                f"KT-related status: {status}"
            )

    student_id_references = re.findall(
        r"\bstudent_id\b",
        normalized_sql,
    )

    if len(student_id_references) < 2:
        raise ValueError(
            "Generated SQL may be missing the student join condition."
        )

    if not re.search(
        r"\bacademic_year\b",
        normalized_sql,
    ) or not re.search(
        r"\bsemester\b",
        normalized_sql,
    ):
        raise ValueError(
            "Generated SQL must account for academic year and semester."
        )


def generate_sql(question, schema):
    """Ask Qwen to translate a natural-language question into MySQL."""

    schema_text = json.dumps(schema, indent=2, default=str)

    prompt = f"""
/no_think

Convert the user's question into exactly one valid MySQL SELECT query.

DATABASE SCHEMA:
{schema_text}

GENERAL SQL RULES:
- Use only tables and columns in the supplied schema.
- Follow the supplied foreign-key relationships.
- Generate read-only SELECT queries only.
- Never generate INSERT, UPDATE, DELETE, DROP, ALTER, or TRUNCATE.
- Do not generate multiple SQL statements.
- Do not invent tables or columns.
- Return SQL only, without Markdown or explanations.

SCHEMA INTERPRETATION AND FILTER SELECTION:
1. Understand what information the user is asking for before choosing
   tables, columns, and filter conditions.

2. Select a column based on its meaning, not merely because its name
   resembles a word in the question.

3. Distinguish between:
   - A descriptive name, such as a full scholarship name.
   - A category or eligibility classification.
   - A type.
   - A status.
   - A numeric amount or percentage.

4. When a question asks for a category, filter on the column that
   represents that category if the schema provides one. Do not assume
   that the category is stored as an exact value in a descriptive name
   column.

5. When a question refers to a status, use the status column rather
   than a name or description column, provided the schema supports it.

6. If the schema contains both scholarship_name and
   eligibility_category and the user asks for students in the EBC
   category, use eligibility_category. Do not use
   scholarship_name = 'EBC' unless the schema and data establish
   that this is correct.

7. Use the supplied schema as the source of truth for available
   columns and relationships. Never invent columns.

8. Use the correct comparison:
   - Exact equality when the intended stored value is known.
   - LIKE when partial text matching is intended.
   - Numeric comparisons for amounts, counts, and percentages.

9. Choose the column that most directly represents the user's intent.
   Do not add unnecessary filters that could exclude valid records.

10. When the user asks who or which students, return useful student
    identifiers or names if those columns are available.

11. For joins, use the supplied relationships and join conditions
    that match the intended records.

12. BRANCH KEYWORD MAPPING:
    When "IT" refers to the college branch, interpret it as the stored
    value 'Information Technology'.
    For attendance questions about IT, if ATTENDANCE_DETAILS.branch
    is the relevant column, use:
    ATTENDANCE_DETAILS.branch = 'Information Technology'
    Do not use branch = 'IT' for this request.
    Apply this mapping only when IT refers to the college branch.

BUSINESS RULES:
1. A KT-related academic status is one of:
   'KT', 'ATKT', 'Internal KT', 'Term Work KT'.

2. An attendance defaulter has:
   ATTENDANCE_DETAILS.attendance_percentage < 75.

3. When a question asks for BOTH KT and defaulter status, join
   ACADEMIC_DETAILS and ATTENDANCE_DETAILS by:
   - student_id
   - academic_year
   - semester

4. When counting students, use COUNT(DISTINCT student_id).

5. Never use ATTENDANCE_DETAILS.branch to determine KT.

QUESTION REQUIREMENT CHECKLIST:
- Identify every condition requested in the question.
- Ensure the SQL implements every requested condition.
- Use columns that represent the requested concepts.
- Ensure selected columns and joins are supported by the schema.
- If required tables or columns are missing, do not invent them.
- Return exactly one read-only SELECT query.

USER QUESTION:
{question}

Return one MySQL SELECT query and nothing else.
"""

    response = ollama.chat(
        model="qwen3:4b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a careful MySQL query generator. "
                    "Interpret the database schema and column meanings "
                    "before choosing SQL filters. "
                    "Return exactly one valid SELECT query."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        options={"temperature": 0},
    )

    model_output = response["message"]["content"]
    sql = extract_sql(model_output)

    validate_question_requirements(
        question=question,
        sql=sql,
        schema=schema,
    )

    return sql
