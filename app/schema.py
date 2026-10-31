
from sqlalchemy import inspect

from app.database import engine


def get_database_schema():
    """Inspect the database and return its tables, columns, and relationships."""

    inspector = inspect(engine)
    schema = {}

    for table_name in inspector.get_table_names():
        columns = inspector.get_columns(table_name)
        primary_key = inspector.get_pk_constraint(table_name)
        foreign_keys = inspector.get_foreign_keys(table_name)

        schema[table_name] = {
            "columns": [
                {
                    "name": column["name"],
                    "type": str(column["type"]),
                }
                for column in columns
            ],
            "primary_key": primary_key.get(
                "constrained_columns", []
            ),
            "foreign_keys": [
                {
                    "column": fk["constrained_columns"],
                    "references_table": fk["referred_table"],
                    "references_column": fk["referred_columns"],
                }
                for fk in foreign_keys
            ],
        }

    return schema


def print_database_schema():
    """Print the inspected database schema."""

    schema = get_database_schema()

    for table_name, details in schema.items():
        print(f"\nTABLE: {table_name}")
        print("Columns:")

        for column in details["columns"]:
            print(f"  - {column['name']} ({column['type']})")

        print("Primary Key:")
        print(f"  {details['primary_key']}")

        print("Foreign Keys:")

        for fk in details["foreign_keys"]:
            print(
                f"  {fk['column']} -> "
                f"{fk['references_table']}"
                f"({fk['references_column']})"
            )
