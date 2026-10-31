
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(DATABASE_URL)


def test_connection():
    try:
        with engine.connect() as connection:
            print("Database connected successfully!")

            result = connection.exec_driver_sql(
                "SELECT DATABASE()"
            )
            active_database = result.scalar()

            print(f"\nPython is connected to: {active_database}")

        inspector = inspect(engine)
        tables = inspector.get_table_names()

        print("\nTables in database:")

        for table in tables:
            print("-", table)

    except Exception as e:
        print("Database connection failed!")
        print(e)


if __name__ == "__main__":
    test_connection()
