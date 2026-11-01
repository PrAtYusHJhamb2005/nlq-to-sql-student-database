
import { useRef, useState } from "react";

const examples = [
  "Which students receive an EBC scholarship?",
  "Who still owes money to the college?",
  "Show students with attendance below 75% in IT.",
  "Which students have KT and attendance below 75%?"
];

export default function App() {
  const [question, setQuestion] = useState("");
  const [role, setRole] = useState("admin");

  const [output, setOutput] = useState(
    "Ready.\n\nStart by entering your first question."
  );

  const [running, setRunning] = useState(false);
  const [awaitingContinue, setAwaitingContinue] = useState(false);
  const [sessionEnded, setSessionEnded] = useState(false);
  const [queryCount, setQueryCount] = useState(0);

  const outputRef = useRef(null);

  async function runQuery(event) {
    event?.preventDefault();

    if (!question.trim() || running || sessionEnded) return;

    const currentQuestion = question.trim();

    setQuestion("");
    setRunning(true);
    setAwaitingContinue(false);

    setOutput((previous) =>
      previous +
      `\n\n${"=".repeat(55)}\n` +
      `\nYOU: ${currentQuestion}\n\n` +
      "Connecting to the Python pipeline...\n"
    );

    try {
      const response = await fetch("http://127.0.0.1:8000/api/query", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          question: currentQuestion,
          role
        })
      });

      if (!response.ok) {
        const message = await response.text();
        setOutput((previous) =>
          previous + `\nAPI ERROR (${response.status})\n${message}`
        );
        return;
      }

      if (!response.body) {
        setOutput((previous) =>
          previous + "\nERROR: Server returned no readable output stream."
        );
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();

        if (done) break;

        const chunk = decoder.decode(value, { stream: true });

        setOutput((previous) => previous + chunk);

        requestAnimationFrame(() => {
          if (outputRef.current) {
            outputRef.current.scrollTop =
              outputRef.current.scrollHeight;
          }
        });
      }

      const remaining = decoder.decode();

      if (remaining) {
        setOutput((previous) => previous + remaining);
      }

      setQueryCount((previous) => previous + 1);
      setAwaitingContinue(true);

    } catch (error) {
      setOutput((previous) =>
        previous +
        "\nCould not connect to the backend.\n\n" +
        "Check that the backend is running at http://127.0.0.1:8000.\n\n" +
        `Details: ${error.message}`
      );

      setAwaitingContinue(true);

    } finally {
      setRunning(false);
    }
  }

  function continueSession() {
    setAwaitingContinue(false);
    setQuestion("");
  }

  function endSession() {
    setAwaitingContinue(false);
    setSessionEnded(true);

    setOutput((previous) =>
      previous + "\n\nSESSION ENDED. Thank you for using the system."
    );
  }

  function startNewSession() {
    setQuestion("");
    setOutput("New session started.\n\nEnter your question.");
    setQueryCount(0);
    setAwaitingContinue(false);
    setSessionEnded(false);
    setRunning(false);
  }

  return (
    <main className="page">
      <header className="header">
        <div>
          <div className="kicker">STUDENT MANAGEMENT DATABASE</div>
          <h1>NLQ-to-SQL Console</h1>
          <p>Ask multiple questions in one query session.</p>
        </div>

        <div className={`status ${running ? "busy" : ""}`}>
          <span className="dot" />
          {running
            ? "RUNNING"
            : sessionEnded
              ? "SESSION ENDED"
              : awaitingContinue
                ? "WAITING"
                : "READY"}
        </div>
      </header>

      <section className="panel input-panel">
        <label htmlFor="question">Natural-language question</label>

        <form onSubmit={runQuery}>
          <textarea
            id="question"
            rows="3"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="For example: Who still owes money to the college?"
            disabled={running || sessionEnded || awaitingContinue}
          />

          <div className="controls">
            <div className="role-control">
              <label htmlFor="role">Demo role</label>

              <select
                id="role"
                value={role}
                onChange={(event) => setRole(event.target.value)}
                disabled={running || queryCount > 0}
              >
                <option value="admin">Admin</option>
                <option value="faculty">Faculty</option>
                <option value="student">Student</option>
              </select>
            </div>

            <button
              type="submit"
              disabled={
                running ||
                sessionEnded ||
                awaitingContinue ||
                !question.trim()
              }
            >
              {running ? "Running pipeline..." : "Run query"}
            </button>
          </div>
        </form>

        <div className="examples">
          <span>EXAMPLES</span>

          {examples.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setQuestion(item)}
              disabled={running || sessionEnded || awaitingContinue}
            >
              {item}
            </button>
          ))}
        </div>
      </section>

      {awaitingContinue && !sessionEnded && (
        <section className="panel input-panel">
          <h3>Would you like to ask another question?</h3>
          <p>
            Queries completed in this session: {queryCount}
          </p>

          <div className="controls">
            <button type="button" onClick={continueSession}>
              Yes, ask another
            </button>

            <button
              type="button"
              className="clear"
              onClick={endSession}
            >
              No, end session
            </button>
          </div>
        </section>
      )}

      {sessionEnded && (
        <section className="panel input-panel">
          <h3>Query session completed</h3>
          <p>Total questions processed: {queryCount}</p>

          <button type="button" onClick={startNewSession}>
            Start new session
          </button>
        </section>
      )}

      <section className="panel terminal-panel">
        <div className="terminal-header">
          <div className="terminal-title">
            <span className="terminal-dot" />
            Query session output
          </div>

          <button
            className="clear"
            type="button"
            onClick={() => setOutput("")}
            disabled={running}
          >
            Clear output
          </button>
        </div>

        <pre
          ref={outputRef}
          className="terminal"
          aria-live="polite"
        >
          {output || "Output cleared."}
        </pre>

        <div className="terminal-footer">
          Continuous query session · Existing Python and MySQL pipeline
        </div>
      </section>

      <footer>
        Local development interface · Qwen3:4b · MySQL
      </footer>
    </main>
  );
}
