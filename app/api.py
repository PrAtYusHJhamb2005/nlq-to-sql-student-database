import re
import sys
import threading
import subprocess
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
MAIN_FILE = ROOT / "app" / "main.py"
RUN_LOCK = threading.Lock()

app = FastAPI(title="NLQ Student Database API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    role: str = "admin"


@app.get("/api/health")
def health():
    return {
        "status": "ready",
        "main_file_exists": MAIN_FILE.exists(),
        "message": "API is ready to launch app.main",
    }


def stream_python_output(question: str, role: str):
    """Run the real CLI and stream its stdout/stderr to the browser."""
    if not MAIN_FILE.exists():
        yield f"ERROR: Could not find {MAIN_FILE}\n"
        return

    source = MAIN_FILE.read_text(encoding="utf-8")

    # Support both versions of the CLI:
    # one that asks only for a question, and one that asks for a role first.
    role_prompt_exists = bool(
        re.search(r"\b(?:role|user_role)\s*=\s*input\s*\(", source, re.I)
    )

    if role_prompt_exists:
        input_text = f"{role.strip()}\n{question.strip()}\n"
    else:
        input_text = f"{question.strip()}\n"

    process = None

    # Avoid running two copies of the CLI at the same time.
    with RUN_LOCK:
        try:
            yield "Starting your existing Python pipeline...\n\n"

            process = subprocess.Popen(
                [sys.executable, "-u", "-m", "app.main"],
                cwd=str(ROOT),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            # The CLI receives its inputs through stdin, not shell commands.
            try:
                process.stdin.write(input_text)
                process.stdin.close()
            except BrokenPipeError:
                # The program may have stopped early, for example if MySQL
                # was unavailable. Continue reading its diagnostic output.
                pass

            # stdout and stderr are combined, preserving their output order.
            for line in process.stdout:
                yield line

            return_code = process.wait()
            yield f"\n\n========== PROCESS FINISHED (exit code {return_code}) ==========\n"

        except Exception as exc:
            yield f"\nBACKEND ERROR: {type(exc).__name__}: {exc}\n"

        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait()


@app.post("/api/query")
def run_query(payload: QueryRequest):
    question = payload.question.strip()

    if not question:
        return StreamingResponse(
            iter(["ERROR: Please enter a question.\n"]),
            media_type="text/plain; charset=utf-8",
        )

    if payload.role.strip().lower() not in {"admin", "faculty", "student"}:
        return StreamingResponse(
            iter(["ERROR: Role must be admin, faculty, or student.\n"]),
            media_type="text/plain; charset=utf-8",
        )

    return StreamingResponse(
        stream_python_output(question, payload.role),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
