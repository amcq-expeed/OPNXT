import { useMemo, useRef, useState } from "react";

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

  const firstStep = steps[0];

  const initials = useMemo(() => {
    if (!userName) return "AI";
    const parts = userName.split(" ").filter(Boolean);
    if (parts.length === 0) return userName.slice(0, 2).toUpperCase();
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  }, [userName]);

  const toggle = () => setOpen((prev) => !prev);

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
              <form className="support-thread__composer">
                <label htmlFor="support-message" className="sr-only">
                  Ask a question
                </label>
                <input id="support-message" type="text" placeholder="Ask a question…" />
                <button type="submit" aria-label="Send message">
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
