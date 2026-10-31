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
    "Ready.\n\nEnter a question and click Run query. The actual output from app.main will appear here."
  );
  const [running, setRunning] = useState(false);
  const outputRef = useRef(null);

  async function runQuery(event) {
    event?.preventDefault();

    if (!question.trim() || running) return;

    setRunning(true);
    setOutput("Connecting to the Python pipeline...\n");

    try {
      const response = await fetch("http://127.0.0.1:8000/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question.trim(),
          role
        })
      });

      if (!response.ok) {
        const message = await response.text();
        setOutput(`API ERROR (${response.status})\n${message}`);
        setRunning(false);
        return;
      }

      if (!response.body) {
        setOutput("ERROR: The server did not return a readable output stream.");
        setRunning(false);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullOutput = "";

      while (true) {
        const { value, done } = await reader.read();

        if (done) break;

        fullOutput += decoder.decode(value, { stream: true });
        setOutput(fullOutput);

        // Keep the latest terminal output visible as it streams in.
        requestAnimationFrame(() => {
          if (outputRef.current) {
            outputRef.current.scrollTop = outputRef.current.scrollHeight;
          }
        });
      }

      fullOutput += decoder.decode();
      setOutput(fullOutput || "The Python process returned no output.");
    } catch (error) {
      setOutput(
        "Could not connect to the backend.\n\n" +
        "Check that the backend is running at http://127.0.0.1:8000.\n\n" +
        `Details: ${error.message}`
      );
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="page">
      <header className="header">
        <div>
          <div className="kicker">STUDENT MANAGEMENT DATABASE</div>
          <h1>NLQ-to-SQL Console</h1>
          <p>Ask a question and inspect the actual Python pipeline output.</p>
        </div>
        <div className={`status ${running ? "busy" : ""}`}>
          <span className="dot" />
          {running ? "RUNNING" : "READY"}
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
            disabled={running}
          />

          <div className="controls">
            <div className="role-control">
              <label htmlFor="role">Demo role</label>
              <select
                id="role"
                value={role}
                onChange={(event) => setRole(event.target.value)}
                disabled={running}
              >
                <option value="admin">Admin</option>
                <option value="faculty">Faculty</option>
                <option value="student">Student</option>
              </select>
            </div>

            <button type="submit" disabled={running || !question.trim()}>
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
              disabled={running}
            >
              {item}
            </button>
          ))}
        </div>
      </section>

      <section className="panel terminal-panel">
        <div className="terminal-header">
          <div className="terminal-title">
            <span className="terminal-dot" />
            Python terminal output
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

        <pre ref={outputRef} className="terminal" aria-live="polite">
          {output || "Output cleared. Run a query to display the pipeline logs."}
        </pre>

        <div className="terminal-footer">
          Combined stdout and stderr from <code>python -m app.main</code>
        </div>
      </section>

      <footer>
        Local development interface · Existing Python and MySQL pipeline
      </footer>
    </main>
  );
}
