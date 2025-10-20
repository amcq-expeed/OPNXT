import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChatMessage,
  ChatSession,
  createGuestChatSession,
  listChatMessages,
  postChatMessage,
} from "../lib/api";

interface SupportWidgetProps {
  userName?: string | null;
  collapsedLabel?: string;
}

const steps = [
  {
    title: "Set up your profile",
    description: "Personalize workspace details and invite collaborators.",
  },
  {
    title: "Connect repositories",
    description: "Sync backlog, docs, and telemetry from your toolchain.",
  },
  {
    title: "Kick off your first initiative",
    description: "Generate a charter and SRS bundle in minutes.",
  },
];

export default function SupportWidget({
  userName,
  collapsedLabel = "Need help?",
}: SupportWidgetProps) {
  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"home" | "messages" | "tasks">("home");
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);

  const [session, setSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const firstStep = steps[0];

  const initials = useMemo(() => {
    if (!userName) return "AI";
    const parts = userName.split(" ").filter(Boolean);
    if (parts.length === 0) return userName.slice(0, 2).toUpperCase();
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  }, [userName]);

  const ensureSession = useCallback(async () => {
    if (session) return session.session_id;
    setLoading(true);
    setNotice("Connecting to support…");
    setError(null);
    try {
      const created = await createGuestChatSession({
        title: "Support Assistant Chat",
        persona: "support",
      });
      setSession(created.session);
      setMessages(created.messages || []);
      setNotice(null);
      return created.session.session_id;
    } catch (err: any) {
      const detail = err?.message || "Unable to connect to support.";
      setError(detail);
      setNotice(null);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [session]);

  useEffect(() => {
    if (!open) return;
    if (activeTab !== "messages") return;
    if (session || loading) return;
    ensureSession().catch(() => {});
  }, [open, activeTab, session, loading, ensureSession]);

  useEffect(() => {
    if (!open || activeTab !== "messages") return;
    const container = transcriptRef.current;
    requestAnimationFrame(() => {
      if (container) {
        container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
      }
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    });
  }, [messages.length, open, activeTab, notice, error]);

  const toggle = () => {
    setOpen((prev) => !prev);
    if (open) {
      setNotice(null);
    }
  };

  const handleSend = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (sending || loading) return;
      const text = draft.trim();
      if (!text) return;
      let optimistic: ChatMessage | null = null;
      try {
        const sessionId = session?.session_id ?? (await ensureSession());
        if (!sessionId) return;
        setSending(true);
        setError(null);
        setNotice("Waiting for support assistant…");
        const userMessage: ChatMessage = {
          message_id: `local-${Date.now()}`,
          session_id: sessionId,
          role: "user",
          content: text,
          created_at: new Date().toISOString(),
        };
        optimistic = userMessage;
        setMessages((prev) => prev.concat(userMessage));
        setDraft("");
        const assistant = await postChatMessage(sessionId, text);
        setMessages((prev) => prev.concat(assistant));
        setNotice(null);
        const latest = await listChatMessages(sessionId);
        if (latest && latest.length) {
          setMessages(latest);
        }
      } catch (err: any) {
        const detail = err?.message || "Unable to send message.";
        setError(detail);
        setNotice(null);
        if (optimistic) {
          setMessages((prev) => prev.filter((msg) => msg.message_id !== optimistic!.message_id));
        }
        setDraft(text);
      } finally {
        setSending(false);
      }
    },
    [draft, sending, loading, session, ensureSession],
  );

  return (
    <div className="support-widget" aria-live="polite">
      <button
        type="button"
        className="support-widget__launcher"
        onClick={toggle}
        aria-expanded={open}
        aria-controls="support-widget-panel"
        aria-label={open ? "Close support assistant" : "Open support assistant"}
      >
        <span className="support-widget__launcher-icon" aria-hidden="true">
          {open ? "✖" : "💬"}
        </span>
        <span className="support-widget__launcher-label">{collapsedLabel}</span>
      </button>

      <div
        id="support-widget-panel"
        className={`support-widget__panel ${open ? "support-widget__panel--open" : ""}`.trim()}
        role="dialog"
        aria-modal="false"
        aria-hidden={!open}
        ref={dialogRef}
      >
        <header className="support-widget__header">
          <div className="support-widget__avatars" aria-hidden="true">
            <span>{initials}</span>
            <span>AI</span>
          </div>
          <div className="support-widget__greeting">
            <p className="support-widget__eyebrow">Hi {userName || "there"} 👋</p>
            <h2>How can we help?</h2>
          </div>
          <button
            type="button"
            className="support-widget__close"
            onClick={() => setOpen(false)}
            aria-label="Close support panel"
          >
            ×
          </button>
        </header>

        <div className="support-widget__body" role="document">
          {activeTab === "home" ? (
            <>
              <button type="button" className="support-card support-card--primary" onClick={() => setActiveTab("messages")}>
                <div className="support-card__body">
                  <span className="support-card__title">Ask a question</span>
                  <span className="support-card__subtitle">AI agent and team can help</span>
                </div>
                <span className="support-card__icon" aria-hidden="true">
                  ?
                </span>
              </button>
              <div className="support-card">
                <div className="support-card__body">
                  <span className="support-card__title">Welcome, {userName?.split(" ")[0] || "Founder"}</span>
                  <span className="support-card__subtitle">{steps.length} steps · About 12 minutes</span>
                </div>
                <div className="support-card__progress">
                  <div className="support-card__progress-bar" style={{ width: "20%" }} />
                </div>
                <button type="button" className="support-card__link" onClick={() => setActiveTab("tasks")}>
                  First step: {firstStep.title}
                </button>
              </div>
            </>
          ) : null}

          {activeTab === "messages" ? (
            <div className="support-thread">
              <div className="support-thread__bubble support-thread__bubble--agent">
                <p>
                  Hi there! You’re speaking with OPNXT Support AI. I’m ready to help you with account,
                  onboarding, or project questions.
                </p>
                <p>How can I assist today?</p>
              </div>
              <div className="support-thread__messages" ref={transcriptRef}>
                {messages.map((msg) => (
                  <div
                    key={msg.message_id}
                    className="support-thread__bubble"
                    style={{
                      background: msg.role === "assistant" ? "rgb(236 240 255)" : "rgb(255 244 239)",
                      justifySelf: msg.role === "assistant" ? "start" : "end",
                    }}
                  >
                    <strong>{msg.role === "assistant" ? "Assistant" : "You"}</strong>
                    <div style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{msg.content}</div>
                  </div>
                ))}
                {error ? (
                  <div
                    role="alert"
                    style={{
                      background: "rgb(255 235 238)",
                      color: "#8a1c1c",
                      padding: "10px 12px",
                      borderRadius: 12,
                    }}
                  >
                    {error}
                  </div>
                ) : null}
                {!error && notice ? (
                  <div
                    role="status"
                    style={{
                      background: "rgb(236 240 255)",
                      color: "#1b2a5a",
                      padding: "10px 12px",
                      borderRadius: 12,
                    }}
                  >
                    {notice}
                  </div>
                ) : null}
                <div ref={bottomRef} aria-hidden="true" />
              </div>
              <form className="support-thread__composer" onSubmit={handleSend}>
                <label htmlFor="support-message" className="sr-only">
                  Ask a question
                </label>
                <input
                  id="support-message"
                  type="text"
                  placeholder={loading ? "Connecting to support…" : "Ask a question…"}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  disabled={loading || sending}
                />
                <button
                  type="submit"
                  aria-label="Send message"
                  disabled={loading || sending || !draft.trim()}
                >
                  ↗
                </button>
              </form>
            </div>
          ) : null}

          {activeTab === "tasks" ? (
            <ul className="support-tasks">
              {steps.map((step) => (
                <li key={step.title}>
                  <strong>{step.title}</strong>
                  <span>{step.description}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        <footer className="support-widget__footer" role="navigation">
          <button
            type="button"
            className={activeTab === "home" ? "support-nav support-nav--active" : "support-nav"}
            onClick={() => setActiveTab("home")}
          >
            <span aria-hidden="true">🏠</span>
            Home
          </button>
          <button
            type="button"
            className={activeTab === "messages" ? "support-nav support-nav--active" : "support-nav"}
            onClick={() => setActiveTab("messages")}
          >
            <span aria-hidden="true">💬</span>
            Messages
          </button>
          <button
            type="button"
            className={activeTab === "tasks" ? "support-nav support-nav--active" : "support-nav"}
            onClick={() => setActiveTab("tasks")}
          >
            <span aria-hidden="true">✅</span>
            Tasks
          </button>
        </footer>
      </div>
    </div>
  );
}
