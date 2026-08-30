/**
 * CodebaseChatbot — Interactive AI Assistant with memory and code citation.
 * Allows users to ask questions like:
 * "Does this project use Celery? Show me the file and lines of code."
 */

import { useEffect, useRef, useState } from "react";
import { api, type ChatMessage } from "../api";

type Props = {
  projectId: string;
  projectName: string;
  isOpen: boolean;
  onClose: () => void;
};

const SUGGESTIONS = [
  "Does this project use Celery? Show me the files and lines of code.",
  "Where is Redis caching implemented in this project?",
  "How does user authentication and password hashing work?",
  "List all API endpoints with their HTTP methods and route paths.",
  "What database models are defined in this project?",
];

function formatMessageContent(text: string) {
  // Simple markdown renderer for code blocks, bold, headers, and bullet points
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let inCodeBlock = false;
  let codeBlockLang = "";
  let codeBuffer: string[] = [];

  lines.forEach((line, idx) => {
    if (line.startsWith("```")) {
      if (inCodeBlock) {
        // End code block
        elements.push(
          <div key={`code-${idx}`} className="chat-code-block">
            {codeBlockLang && <div className="chat-code-lang">{codeBlockLang}</div>}
            <pre>
              <code>{codeBuffer.join("\n")}</code>
            </pre>
          </div>
        );
        codeBuffer = [];
        inCodeBlock = false;
      } else {
        // Start code block
        inCodeBlock = true;
        codeBlockLang = line.replace("```", "").trim();
      }
      return;
    }

    if (inCodeBlock) {
      codeBuffer.push(line);
      return;
    }

    if (line.startsWith("### ")) {
      elements.push(<h4 key={idx} className="chat-h4">{line.replace("### ", "")}</h4>);
    } else if (line.startsWith("## ")) {
      elements.push(<h3 key={idx} className="chat-h3">{line.replace("## ", "")}</h3>);
    } else if (line.startsWith("# ")) {
      elements.push(<h2 key={idx} className="chat-h2">{line.replace("# ", "")}</h2>);
    } else if (line.startsWith("- ") || line.startsWith("* ")) {
      elements.push(
        <li key={idx} className="chat-li">
          {renderInlineFormatting(line.substring(2))}
        </li>
      );
    } else if (line.trim() === "") {
      elements.push(<div key={idx} className="chat-spacer" />);
    } else {
      elements.push(<p key={idx} className="chat-p">{renderInlineFormatting(line)}</p>);
    }
  });

  if (inCodeBlock && codeBuffer.length) {
    elements.push(
      <div key="code-end" className="chat-code-block">
        <pre><code>{codeBuffer.join("\n")}</code></pre>
      </div>
    );
  }

  return elements;
}

function renderInlineFormatting(text: string) {
  // Parse `inline code` and **bold**
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={i} className="chat-inline-code">{part.slice(1, -1)}</code>;
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

export function CodebaseChatbot({ projectId, projectName, isOpen, onClose }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (!projectId || !isOpen) return;
    loadHistory();
  }, [projectId, isOpen]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const loadHistory = async () => {
    try {
      const history = await api.getChatHistory(projectId);
      setMessages(history);
    } catch {
      // Ignored
    }
  };

  const handleSend = async (queryText?: string) => {
    const text = (queryText || input).trim();
    if (!text || loading) return;

    setInput("");
    setError(null);

    // Optimistic user message
    const tempUserMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      project_id: projectId,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setLoading(true);

    try {
      const reply = await api.sendChatMessage(projectId, text);
      setMessages((prev) => [...prev.filter((m) => m.id !== tempUserMsg.id), tempUserMsg, reply]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate response");
    } finally {
      setLoading(false);
    }
  };

  const handleClear = async () => {
    if (!window.confirm("Clear chat conversation memory for this project?")) return;
    try {
      await api.clearChatHistory(projectId);
      setMessages([]);
    } catch {
      // Ignored
    }
  };

  if (!isOpen) return null;

  return (
    <div className="chat-modal">
      <div className="chat-header">
        <div className="chat-header-info">
          <div className="chat-badge-ai">AI AGENT</div>
          <h3>Codebase Assistant</h3>
          <span className="chat-subtitle">{projectName}</span>
        </div>
        <div className="chat-header-actions">
          {messages.length > 0 && (
            <button
              type="button"
              className="chat-btn-clear"
              onClick={handleClear}
              title="Clear chat memory"
            >
              Clear Memory
            </button>
          )}
          <button type="button" className="chat-btn-close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
      </div>

      <div className="chat-body">
        {messages.length === 0 && (
          <div className="chat-empty">
            <div className="chat-empty-icon">💬</div>
            <h4>Ask anything about this project</h4>
            <p>
              I have full access to the source code, routes, database schemas, and background tasks.
              Ask me to verify specific frameworks, find functions, or explain how data flows.
            </p>
            <div className="chat-suggestions">
              {SUGGESTIONS.map((s, i) => (
                <button
                  key={i}
                  type="button"
                  className="chat-suggestion-chip"
                  onClick={() => handleSend(s)}
                >
                  ⚡ {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <div key={m.id} className={`chat-message ${m.role}`}>
            <div className="chat-avatar">
              {m.role === "user" ? "👤" : "🤖"}
            </div>
            <div className="chat-bubble">
              <div className="chat-bubble-header">
                <span className="chat-author">{m.role === "user" ? "You" : "Hover AI Agent"}</span>
                <span className="chat-time">
                  {new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </span>
              </div>
              <div className="chat-text">
                {formatMessageContent(m.content)}
              </div>
              {m.sources && m.sources.length > 0 && (
                <div className="chat-sources">
                  <span className="chat-sources-label">Cited Files:</span>
                  <div className="chat-sources-chips">
                    {m.sources.map((src, i) => (
                      <span key={i} className="chat-source-chip">
                        📄 {src.file} {src.symbol ? `(${src.symbol})` : ""}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="chat-message assistant">
            <div className="chat-avatar">🤖</div>
            <div className="chat-bubble thinking">
              <div className="chat-thinking-dots">
                <span />
                <span />
                <span />
              </div>
              <span className="chat-thinking-text">Searching codebase & verifying line numbers...</span>
            </div>
          </div>
        )}

        {error && <div className="chat-error">{error}</div>}
        <div ref={messagesEndRef} />
      </div>

      <form
        className="chat-footer"
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
      >
        <input
          type="text"
          className="chat-input"
          placeholder="Ask a question about files, lines of code, tech stack, endpoints..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
        />
        <button type="submit" className="chat-send-btn" disabled={!input.trim() || loading}>
          {loading ? "..." : "Send"}
        </button>
      </form>
    </div>
  );
}
