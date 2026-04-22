import { useState, useRef, useEffect } from "react";

export default function QAPanel({ reportId, disabled }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  async function handleSend() {
    const question = input.trim();
    if (!question || thinking || disabled) return;

    setInput("");
    setError(null);
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setThinking(true);

    try {
      const res = await fetch("/api/qa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reportId, question }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Request failed");
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: data.answer },
      ]);
    } catch (err) {
      setError(err.message);
    } finally {
      setThinking(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="qa-panel">
      <div className="section-heading">Ask questions about this report</div>
      <div className="qa-messages">
        {messages.length === 0 && !thinking && (
          <span style={{ color: "#475569", fontSize: "0.82rem" }}>
            Ask anything about the audit results — e.g. "Why did the technical
            check fail?" or "Which nodes passed signature verification?"
          </span>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`qa-msg ${m.role}`}>
            {m.text}
          </div>
        ))}
        {thinking && (
          <div className="qa-msg thinking">Thinking…</div>
        )}
        <div ref={bottomRef} />
      </div>
      {error && <div className="error-text">{error}</div>}
      <div className="qa-input-row">
        <textarea
          className="qa-input"
          rows={2}
          placeholder="Ask a question… (Enter to send)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled || thinking}
        />
        <button
          className="btn btn-primary"
          onClick={handleSend}
          disabled={disabled || thinking || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
