import ollama


def generate_natural_language_answer(
    question,
    sql,
    rows
):
    """
    Convert database results into a natural-language answer.
    """

    prompt = f"""
You are the result narration agent for a student management database.

Answer the user's question using ONLY the database results provided below.

Do not invent facts.
Do not add information that is not present in the results.
Do not modify or reinterpret numerical values.
If the result contains no rows, clearly say that no matching records were found.
Keep the answer concise and easy to understand.

USER QUESTION:
{question}

SQL USED:
{sql}

DATABASE RESULTS:
{rows}

Provide only the final natural-language answer.
"""

    response = ollama.chat(
        model="qwen3:4b",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response["message"]["content"]