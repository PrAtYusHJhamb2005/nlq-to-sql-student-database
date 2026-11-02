# NLQ-to-SQL Student Database

A natural-language interface for querying a MySQL-based student management database. Instead of writing SQL manually, a user can ask questions in plain English. The application maps the question to relevant database tables, generates a read-only SQL query with a local LLM, validates the query, checks demo-role permissions, executes it, and explains the result.

> **Project status:** Active development / prototype. The schema-mapping and query-selection logic is being iterated on, so generated SQL and selected tables should be checked during testing.

## Overview

The project follows a multi-stage, three-tier query pipeline:

1. **Schema mapping** — inspects the database schema and identifies relevant tables using exact keyword matching, fuzzy matching (RapidFuzz), and semantic similarity (Ollama embeddings). Foreign-key paths are added when needed to connect selected tables.
2. **Tier 1 — SQL generation** — sends the question and relevant schema to Qwen3:4b to generate a MySQL `SELECT` query.
3. **Tier 2 — validation and access control** — parses and validates the generated SQL against the full database schema, applies read-only query restrictions and a result limit, then checks whether the selected demo role can access every referenced table.
4. **Tier 3 — execution and narration** — executes the approved query through SQLAlchemy and uses the LLM to turn the returned records into a natural-language answer.

The schema mapper reduces the schema context sent to the SQL-generation model. The guardrail independently validates generated SQL against the **full schema**, rather than trusting the mapper's selected subset.

## Features

- Ask database questions in natural language.
- Discover database tables, columns, primary keys, and foreign-key relationships through SQLAlchemy inspection.
- Combine exact, fuzzy, and semantic table matching.
- Add foreign-key bridge tables between selected tables.
- Generate MySQL read-only `SELECT` queries with Qwen3:4b.
- Parse SQL with SQLGlot and reject non-SELECT or multiple-statement queries.
- Validate referenced tables and columns against the database schema.
- Apply a maximum result size of 200 rows and a maximum of 6 joins.
- Apply demo table-level access rules for `admin`, `faculty`, and `student`.
- Execute queries and produce a natural-language explanation.
- Use a React interface to stream pipeline output and ask multiple independent questions in a session.
- Accept multiline questions in the UI by normalizing whitespace before passing input to the CLI.

## Technology stack

| Layer | Technologies |
|---|---|
| Language / backend | Python, FastAPI, Uvicorn |
| LLM and embeddings | Ollama, Qwen3:4b, nomic-embed-text |
| Database | MySQL, SQLAlchemy, PyMySQL |
| SQL parsing and validation | SQLGlot |
| Schema matching | RapidFuzz, NumPy, semantic embeddings |
| Frontend | React, Vite, JavaScript |

## Database schema

The application discovers the schema from the configured MySQL database at runtime. The current project database is designed around student-management information and includes tables such as:

- `student_personal_data`
- `DEPARTMENT`
- `COURSE`
- `ATTENDANCE_DETAILS`
- `ACADEMIC_DETAILS`
- `ACADEMIC_STATS`
- `CGPA_DETAILS`
- `FEES_DETAILS`
- `SCHOLARSHIP_DETAILS`
- `STUDENT_HEALTH`
- `EXTRACURRICULAR_DETAILS`
- `TIMETABLE`
- `FACULTY`

The database must already exist, with tables and relationships compatible with the application's schema and prompts. This repository does not currently provide a database dump or a complete seed-data script.

## Architecture

```text
User question
     |
     v
Schema inspection (MySQL)
     |
     v
Schema mapper
  |-- Exact keyword matching
  |-- Fuzzy matching
  |-- Semantic matching
  |-- Foreign-key bridge selection
     |
     v
Relevant schema + question
     |
     v
Tier 1: Qwen3:4b SQL generation
     |
     v
Tier 2A: SQL guardrail
  |-- One SELECT statement only
  |-- Table and column validation
  |-- Block risky operations/functions
  |-- Limit result rows and joins
     |
     v
Tier 2B: Demo-role access control
     |
     v
Tier 3A: MySQL query execution
     |
     v
Tier 3B: Natural-language answer
     |
     v
Answer and streamed pipeline output
```

## Repository structure

```text
nlq-to-sql-student-database/
├── app/
│   ├── __init__.py
│   ├── api.py                 # FastAPI endpoint and CLI output streaming
│   ├── main.py                # CLI entry point and query pipeline
│   ├── database.py            # MySQL connection
│   ├── schema.py              # Runtime schema inspection
│   ├── schema_mapper.py       # Exact, fuzzy, semantic table selection
│   ├── semantic_matcher.py   # Table descriptions and embeddings
│   ├── sql_translator.py      # Natural language to MySQL SELECT
│   ├── guardrail.py           # SQL safety and schema validation
│   ├── access_control.py      # Demo-role table permissions
│   ├── executor.py            # SQL execution
│   └── narrator.py            # Results to natural-language answer
├── frontend/
│   ├── src/
│   │   └── App.jsx            # React query interface
│   ├── package.json
│   └── vite.config.js
├── requirements.txt
└── README.md
```

## Prerequisites

Install and configure the following before running the project:

- Python 3.11 or newer (a Python version supported by the listed packages is recommended).
- Node.js and npm.
- MySQL Server with the project database and compatible tables.
- [Ollama](https://ollama.com/) running locally.
- Git.

Pull the models used by the application:

```bash
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

Make sure the Ollama service is running before using semantic matching or generating answers. Depending on your installation, Ollama may already run as a background application; otherwise start it with:

```bash
ollama serve
```

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/PrAtYusHJhamb2005/nlq-to-sql-student-database.git
cd nlq-to-sql-student-database
```

### 2. Create and activate a Python virtual environment

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Python dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install numpy rapidfuzz
```

### 4. Configure MySQL

Create a local `.env` file in the repository root. Do not commit this file.

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=your_mysql_username
DB_PASSWORD=your_mysql_password
DB_NAME=student_management_db
```

Update the values for your own MySQL installation. Ensure the database and required tables exist before starting the application.

### 5. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

## Run the application

Open separate terminal windows from the repository root.

### Terminal 1 — Backend API

Activate the virtual environment, then run:

```bash
source .venv/bin/activate
uvicorn app.api:app --reload --host 127.0.0.1 --port 8000
```

The API health endpoint is available at:

`http://127.0.0.1:8000/api/health`

### Terminal 2 — React frontend

```bash
cd frontend
npm run dev
```

Open the local URL printed by Vite (normally `http://127.0.0.1:5173`).

### Optional — Run the CLI directly

From the repository root, with the virtual environment active:

```bash
python -m app.main
```

The CLI asks for a demo role and then accepts questions in a continuous session.

## Example questions

Try questions such as:

- Which students receive an EBC scholarship?
- Who still owes money to the college?
- Show students with attendance below 75% in IT.
- Which students have KT and attendance below 75%?
- Find students with the lowest grade point average.
- What subjects and courses are offered?

The exact answer depends on the data and schema in your local MySQL database.

## Demo roles

The current access-control layer applies table-level permissions:

| Role | Intended access |
|---|---|
| `admin` | All configured project tables |
| `faculty` | Academic, attendance, course, department, extracurricular, faculty, CGPA, and timetable tables |
| `student` | Course, department, and timetable tables |

These are prototype/demo permissions. They are not a substitute for production authentication, row-level security, or a fully audited authorization system.

## Safety notes and current limitations

- The SQL pipeline is designed to accept one read-only `SELECT` statement. The guardrail rejects non-SELECT statements, multiple statements, invalid table/column references, selected risky functions, nested subqueries, and CTEs under the current policy.
- Queries are capped at 200 rows and 6 joins by the current guardrail configuration.
- The access-control layer enforces table-level demo roles; it does not implement row-level access or per-column permissions.
- The frontend's multi-question session is a sequence of independent questions. It does not currently preserve conversational context between questions.
- Semantic matching requires the local Ollama embedding model. If semantic matching is unavailable, the mapper falls back to lexical matches where possible.
- LLM-generated SQL can still be logically incorrect even when it passes syntax, schema, and safety checks. Review results and test with non-sensitive development data.
- Do not expose the local API publicly or use real student personal data without appropriate authentication, authorization, privacy safeguards, and institutional approval.

## Development notes

- Table descriptions and semantic test questions are maintained in `app/semantic_matcher.py`.
- Table keywords, matching thresholds, candidate selection, and foreign-key bridge logic are maintained in `app/schema_mapper.py`.
- SQL generation instructions and project-specific business rules are maintained in `app/sql_translator.py`.
- SQL restrictions and result limits are maintained in `app/guardrail.py`.
- Demo-role table permissions are maintained in `app/access_control.py`.

## Contributing / feedback

This is an actively developed project. When reporting an issue, include:

1. The natural-language question used.
2. The tables selected by the schema mapper.
3. The generated SQL (remove any sensitive values first).
4. The guardrail or execution output.
5. Relevant environment details, without sharing credentials or personal data.

---

**Built as an end-to-end project exploring natural-language database querying, LLM-based SQL generation, schema retrieval, SQL validation, and database access control.**
