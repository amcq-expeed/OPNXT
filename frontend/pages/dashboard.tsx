import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import {
  CatalogIntent,
  formatCatalogIntentPrompt,
  listCatalogIntents,
  trackEvent,
} from "../lib/api";
import { useUserContext } from "../lib/user-context";

type QuickIntent = {
  intentId: string | null;
  title: string;
  description: string;
  prefill: string;
  group: string;
  icon: string;
  deliverables: string[];
};

const DEFAULT_ICON = "💡";

const fallbackIntents: QuickIntent[] = [
  {
    intentId: null,
    title: "Capture a new initiative",
    description: "Map objectives, scope, and risks so every team aligns before kickoff.",
    prefill:
      "We are kicking off a new initiative. Help capture objectives, key stakeholders, scope boundaries, primary flows, and top risks so that we can produce an audit-ready requirements package.",
    group: "Capture & Plan",
    icon: "🧭",
    deliverables: ["Project Charter", "Business Requirements"],
  },
  {
    intentId: null,
    title: "Strengthen an in-flight doc",
    description: "Review an existing specification and close gaps with guided prompts.",
    prefill:
      "We have a draft requirements document that needs refinement. Ask clarifying questions, tighten acceptance criteria, and identify any missing non-functional requirements before sign-off.",
    group: "Improve & Govern",
    icon: "🛡️",
    deliverables: ["Redline Suggestions"],
  },
  {
    intentId: null,
    title: "Explore roadmap scenarios",
    description: "Co-create a feature backlog with rationale, KPIs, and release framing.",
    prefill:
      "We need to brainstorm roadmap scenarios for an upcoming planning session. Help uncover user value, success metrics, and feature swimlanes so we can turn it into an actionable backlog.",
    group: "Deliver & Execute",
    icon: "🚀",
    deliverables: ["Feature Backlog"],
  },
  {
    intentId: null,
    title: "Pressure-test a concept",
    description: "Validate an idea against governance, compliance, and launch readiness.",
    prefill:
      "I have a product concept to validate. Help collect stakeholder feedback themes, map approval checkpoints, and highlight compliance or security risks we must address before green-lighting.",
    group: "Improve & Govern",
    icon: "🧪",
    deliverables: ["Readiness Checklist"],
  },
];

function mapCatalogIntent(intent: CatalogIntent): QuickIntent {
  return {
    intentId: intent.intent_id || null,
    title: intent.title,
    description: intent.description,
    prefill: intent.prefill_prompt,
    group: intent.group,
    icon: intent.icon || DEFAULT_ICON,
    deliverables: intent.deliverables || [],
  };
}

export default function DashboardPage() {
  const router = useRouter();
  const { persona } = useUserContext();
  const [draft, setDraft] = useState("");
  const [activeCard, setActiveCard] = useState<string | null>(null);
  const [pendingCard, setPendingCard] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [intents, setIntents] = useState<QuickIntent[]>(fallbackIntents);
  const [catalogLoading, setCatalogLoading] = useState<boolean>(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [catalogIntentMap, setCatalogIntentMap] = useState<Map<string, CatalogIntent>>(new Map());

  const heroHeadline = useMemo(
    () => ({
      primary: "What should we capture next?",
      secondary:
        "Launch a guided copilot to capture requirements, strengthen governance, or explore new delivery scenarios—all without leaving your workspace.",
    }),
    [],
  );

  useEffect(() => {
    let cancelled = false;
    setCatalogLoading(true);
    setCatalogError(null);
    listCatalogIntents(persona || undefined)
      .then((items) => {
        if (cancelled) return;
        if (!Array.isArray(items) || items.length === 0) return;
        setIntents(items.map(mapCatalogIntent));
        setCatalogIntentMap(new Map(items.map((item) => [item.intent_id, item])));
      })
      .catch((error: any) => {
        if (cancelled) return;
        const detail = error?.message || "Unable to load catalog intents right now.";
        setCatalogError(detail);
      })
      .finally(() => {
        if (!cancelled) setCatalogLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [persona]);

  const quickStarts = useMemo(() => intents.slice(0, 4), [intents]);
  const additionalIntents = useMemo(() => intents.slice(4), [intents]);
  const supportingIntents = useMemo(() => additionalIntents.slice(0, 6), [additionalIntents]);

  const launchChat = (prefill: string) => {
    const message = prefill.trim();
    const query = encodeURIComponent(message || "Outline a new initiative");
    router.push(`/start?prefill=${query}`);
  };

  const launchQuickStart = useCallback(
    async (idea: QuickIntent) => {
      if (pendingCard) return;
      setActiveCard(idea.title);
      setPendingCard(idea.title);
      setStatusMessage("Opening accelerator…");
      setErrorMessage(null);
      trackEvent("intent_launch_clicked", {
        intentId: idea.intentId,
        title: idea.title,
        group: idea.group,
        source: "dashboard-card",
      });
      try {
        if (idea.intentId) {
          const params = new URLSearchParams({ source: "dashboard" });
          const target = `/accelerators/${encodeURIComponent(idea.intentId)}?${params.toString()}`;
          await router.push(target);
          return;
        }
        const intent = catalogIntentMap.get(idea.intentId || "");
        const prompt = intent ? formatCatalogIntentPrompt(intent) : idea.prefill;
        setStatusMessage("Opening chat…");
        launchChat(prompt);
      } catch (error: any) {
        const detail = error?.message || "We couldn't start that quick capture. Try again.";
        setErrorMessage(detail);
      } finally {
        setStatusMessage(null);
        setPendingCard(null);
        setActiveCard(null);
      }
    },
    [pendingCard, router, persona, catalogIntentMap],
  );

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    launchChat(draft);
    setDraft("");
  };

  return (
    <div className="dashboard-shell" aria-live="polite">
      <header className="dashboard-hero">
        <span className="dashboard-hero__eyebrow">OPNXT workspace</span>
        <div className="dashboard-hero__title">
          <h1 className="dashboard-hero__headline" aria-live="polite">
            {heroHeadline.primary}
          </h1>
          <p className="dashboard-hero__copy">{heroHeadline.secondary}</p>
        </div>
      </header>

      {statusMessage && (
        <div className="dashboard-status" role="status">
          {statusMessage}
        </div>
      )}
      {errorMessage && (
        <div className="dashboard-status dashboard-status--error" role="alert">
          {errorMessage}
        </div>
      )}

      <main className="dashboard-main">
        <section className="dashboard-actions" aria-label="Guided accelerators">
          <div className="dashboard-actions__panel" role="list">
            {quickStarts.map((idea) => {
              const isActive = activeCard === idea.title;
              const isPending = pendingCard === idea.title;
              const tooltipContent = [
                idea.group ? `Category: ${idea.group}` : null,
                idea.deliverables.length > 0 ? `Outputs: ${idea.deliverables.join(", ")}` : null,
              ]
                .filter(Boolean)
                .join(" • ");
              const tooltipId = `quick-card-${(idea.intentId || idea.title)
                .toLowerCase()
                .replace(/[^a-z0-9]+/g, "-")}`;
              const buttonClasses = ["quick-card"];
              if (isActive) buttonClasses.push("quick-card--active");
              if (isPending) buttonClasses.push("quick-card--pending");
              return (
                <button
                  key={idea.title}
                  type="button"
                  className={buttonClasses.join(" ")}
                  onClick={() => launchQuickStart(idea)}
                  aria-pressed={isActive}
                  aria-busy={isPending || undefined}
                  aria-describedby={tooltipContent ? tooltipId : undefined}
                  disabled={Boolean(pendingCard)}
                >
                  <span className="quick-card__icon" aria-hidden="true">
                    {idea.icon}
                  </span>
                  <span className="quick-card__body">
                    <span className="quick-card__title">{idea.title}</span>
                    <span className="quick-card__description">{idea.description}</span>
                  </span>
                  <span className="quick-card__cta" aria-hidden="true">
                    {isPending ? "Launching…" : "Launch"}
                    <svg viewBox="0 0 20 20" focusable="false" aria-hidden="true">
                      <path
                        d="M7.5 5l4.5 5-4.5 5"
                        stroke="currentColor"
                        strokeWidth="1.6"
                        fill="none"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </span>
                  {tooltipContent && (
                    <span id={tooltipId} className="quick-card__tooltip" role="tooltip">
                      {tooltipContent}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
          {(catalogLoading || catalogError || supportingIntents.length > 2) && (
            <div className="dashboard-actions__support" aria-live="polite">
              {catalogError && (
                <div className="dashboard-actions__status" role="alert">
                  {catalogError}
                </div>
              )}
              {catalogLoading && <span className="dashboard-actions__chip" aria-busy="true">Loading…</span>}
              {supportingIntents.slice(2).map((idea) => (
                <button
                  key={idea.intentId || idea.title}
                  type="button"
                  className="dashboard-actions__chip"
                  onClick={() => {
                    trackEvent("intent_prefill_selected", {
                      intentId: idea.intentId,
                      title: idea.title,
                      group: idea.group,
                      source: "dashboard-chip",
                    });
                    if (idea.intentId) {
                      const params = new URLSearchParams({ source: "dashboard-chip" });
                      router.push(
                        `/accelerators/${encodeURIComponent(idea.intentId)}?${params.toString()}`,
                      );
                      return;
                    }
                    const intent = catalogIntentMap.get(idea.intentId || "");
                    const prompt = intent ? formatCatalogIntentPrompt(intent) : idea.prefill;
                    launchChat(prompt);
                  }}
                >
                  <span aria-hidden="true">{idea.icon}</span>
                  <span>{idea.title}</span>
                </button>
              ))}
            </div>
          )}
        </section>
      </main>

      <section className="dashboard-composer" aria-label="Start a chat">
        <form className="dashboard-composer__form" onSubmit={handleSubmit}>
          <label className="sr-only" htmlFor="dashboard-chat-input">
            Describe what you need help with
          </label>
          <textarea
            id="dashboard-chat-input"
            className="dashboard-composer__input"
            placeholder="Send a message..."
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={1}
          />
          <div className="dashboard-composer__footer">
            <div className="dashboard-composer__meta">
              <span className="dashboard-composer__status">No project selected</span>
              <span className="dashboard-composer__model">Adaptive model: Auto (OPNXT)</span>
              <Link href="/templates" className="dashboard-composer__link">
                Browse OPNXT templates
              </Link>
            </div>
            <div className="dashboard-composer__actions">
              <button
                type="button"
                className="dashboard-composer__icon-btn"
                aria-label="Add attachment"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                  <path
                    d="M8.5 12.75l4.95-4.95a2.5 2.5 0 113.54 3.54l-6.01 6.01a3.5 3.5 0 01-4.95-4.95l6.01-6.01"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
              <button className="dashboard-composer__send" type="submit">
                <span>Send</span>
                <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
                  <path
                    d="M3.5 9.5l12-5-5 12-1.5-4.5-4.5-1.5z"
                    fill="currentColor"
                    stroke="currentColor"
                    strokeWidth="0.6"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>
          </div>
        </form>
      </section>
    </div>
  );
}
