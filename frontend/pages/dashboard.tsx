import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/router";
import {
  CatalogIntent,
  ChatMessage,
  ChatModelOption,
  ChatSession,
  createGuestChatSession,
  formatCatalogIntentPrompt,
  getChatSession,
  listCatalogIntents,
  listChatMessages,
  listChatModels,
  postChatMessage,
  trackEvent,
} from "../lib/api";
import { useUserContext } from "../lib/user-context";
import {
  getModelPreference,
  setModelPreference,
} from "../lib/modelPreference";

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
  const [modelOptions, setModelOptions] = useState<ChatModelOption[]>([]);
  const [modelLoading, setModelLoading] = useState<boolean>(false);
  const [modelError, setModelError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>("adaptive");
  const [guestSession, setGuestSession] = useState<ChatSession | null>(null);
  const [guestMessages, setGuestMessages] = useState<ChatMessage[]>([]);
  const [guestLoading, setGuestLoading] = useState<boolean>(false);
  const [guestSending, setGuestSending] = useState<boolean>(false);
  const [guestError, setGuestError] = useState<string | null>(null);
  const [chatNotice, setChatNotice] = useState<string | null>(null);
  const [deepLinkError, setDeepLinkError] = useState<string | null>(null);

  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const askBottomRef = useRef<HTMLDivElement | null>(null);

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

  useEffect(() => {
    let cancelled = false;
    setModelLoading(true);
    setModelError(null);
    listChatModels()
      .then((options) => {
        if (cancelled) return;
        const filtered = Array.isArray(options)
          ? options.filter((opt) => !opt.provider.startsWith("search"))
          : [];
        setModelOptions(filtered);
        const persisted = getModelPreference();
        if (persisted) {
          if (persisted.provider === "adaptive") {
            setSelectedModel("adaptive");
          } else {
            const match = filtered.find(
              (opt) =>
                opt.provider === persisted.provider &&
                opt.model === persisted.model,
            );
            if (match) {
              setSelectedModel(`${match.provider}:${match.model}`);
            }
          }
        }
      })
      .catch((error: any) => {
        if (cancelled) return;
        setModelError(error?.message || "Unable to load model catalog right now.");
      })
      .finally(() => {
        if (!cancelled) setModelLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const resetAskExperience = useCallback(() => {
    setGuestSession(null);
    setGuestMessages([]);
    setGuestError(null);
    setChatNotice(null);
    setDeepLinkError(null);
    void router.replace({ pathname: router.pathname }, undefined, { shallow: true });
  }, []);

  const resolveModelOverrides = useCallback(() => {
    if (!selectedModel || selectedModel === "adaptive") {
      return { provider: null as string | null, model: null as string | null };
    }
    const [provider, ...rest] = selectedModel.split(":");
    const model = rest.join(":") || null;
    if (!provider || provider === "adaptive") {
      return { provider: null, model: null };
    }
    return { provider, model };
  }, [selectedModel]);

  const quickStarts = useMemo(() => intents.slice(0, 4), [intents]);
  const additionalIntents = useMemo(() => intents.slice(4), [intents]);
  const supportingIntents = useMemo(() => additionalIntents.slice(0, 6), [additionalIntents]);

  useEffect(() => {
    const sessionId = typeof router.query.session === "string" ? router.query.session : null;
    if (!sessionId || guestSession) return;
    let cancelled = false;
    setGuestLoading(true);
    setGuestError(null);
    setChatNotice("Loading chat history…");
    getChatSession(sessionId)
      .then((payload) => {
        if (cancelled) return;
        const session = payload?.session;
        const messages = payload?.messages || [];
        if (!session) {
          throw new Error("Session not found");
        }
        setGuestSession(session);
        setGuestMessages(messages);
        setChatNotice(null);
        setDeepLinkError(null);
        trackEvent("dashboard_chat_session_loaded", { sessionId });
      })
      .catch((error: any) => {
        if (cancelled) return;
        const detail = error?.message || "Unable to load that chat session.";
        setDeepLinkError(detail);
        setGuestSession(null);
        setGuestMessages([]);
        setChatNotice(null);
      })
      .finally(() => {
        if (!cancelled) {
          setGuestLoading(false);
          setChatNotice(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [router.query.session, guestSession]);

  const launchChat = useCallback(
    (prefill: string) => {
      const message = prefill.trim();
      if (!message) return;
      resetAskExperience();
      setDraft(message);
      setErrorMessage(null);
      setStatusMessage(null);
      requestAnimationFrame(() => composerRef.current?.focus());
    },
    [resetAskExperience],
  );

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
    [pendingCard, router, catalogIntentMap, launchChat],
  );

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const message = draft.trim();
    if (!message) return;
    const { provider, model } = resolveModelOverrides();

    if (!guestSession) {
      setGuestLoading(true);
      setChatNotice("Launching Ask OPNXT…");
      setGuestError(null);
      try {
        const payload: {
          title: string;
          initial_message: string;
          persona?: string;
          provider?: string | null;
          model?: string | null;
        } = {
          title: "Ask OPNXT",
          initial_message: message,
        };
        if (persona) payload.persona = persona;
        if (provider) payload.provider = provider;
        if (model) payload.model = model;
        const sessionWithMessages = await createGuestChatSession(payload);
        setGuestSession(sessionWithMessages.session);
        setGuestMessages(sessionWithMessages.messages || []);
        setDraft("");
        setErrorMessage(null);
        trackEvent("dashboard_ask_started", { source: "dashboard", provider: provider ?? "adaptive" });
      } catch (error: any) {
        const detail = error?.message || "Unable to start Ask OPNXT right now.";
        setGuestError(detail);
        setErrorMessage(detail);
      } finally {
        setGuestLoading(false);
        setChatNotice(null);
      }
      return;
    }

    setGuestSending(true);
    setChatNotice("Waiting for assistant response…");
    setGuestError(null);
    const optimistic: ChatMessage = {
      message_id: `local-${Date.now()}`,
      session_id: guestSession.session_id,
      role: "user",
      content: message,
      created_at: new Date().toISOString(),
    };
    setGuestMessages((prev) => prev.concat(optimistic));
    setDraft("");
    try {
      await postChatMessage(guestSession.session_id, message, {
        provider: provider ?? undefined,
        model: model ?? undefined,
      });
      const latest = await listChatMessages(guestSession.session_id);
      setGuestMessages(latest ?? []);
      trackEvent("dashboard_ask_message_sent", {
        sessionId: guestSession.session_id,
        provider: provider ?? "adaptive",
      });
    } catch (error: any) {
      const detail = error?.message || "Unable to send message right now.";
      setGuestError(detail);
      setGuestMessages((prev) => prev.filter((msg) => msg.message_id !== optimistic.message_id));
      setDraft(message);
    } finally {
      setGuestSending(false);
      setChatNotice(null);
    }
  };

  useEffect(() => {
    if (!guestMessages.length) return;
    requestAnimationFrame(() => askBottomRef.current?.scrollIntoView({ behavior: "smooth" }));
  }, [guestMessages.length]);

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
            ref={composerRef}
            rows={1}
            disabled={guestLoading || guestSending}
          />
          <div className="dashboard-composer__footer">
            <div className="dashboard-composer__meta">
              <span className="dashboard-composer__status">
                {guestSession ? "Ask OPNXT session active" : "No project selected"}
              </span>
              <label className="dashboard-composer__model-select">
                <span>Model</span>
                <select
                  value={selectedModel}
                  onChange={(event) => {
                    const value = event.target.value;
                    setSelectedModel(value);
                    const choice = modelOptions.find(
                      (opt) => `${opt.provider}:${opt.model}` === value,
                    );
                    if (choice && !choice.adaptive) {
                      setModelPreference(choice.provider, choice.model);
                    } else if (value === "adaptive") {
                      setModelPreference("adaptive", "auto");
                    }
                  }}
                  disabled={modelLoading || modelOptions.length === 0}
                  className="select"
                >
                  <option value="adaptive">Adaptive model: Auto (OPNXT)</option>
                  {modelOptions.map((opt) => (
                    <option
                      key={`${opt.provider}:${opt.model}`}
                      value={`${opt.provider}:${opt.model}`}
                      disabled={!opt.available && !opt.adaptive}
                    >
                      {opt.label}
                      {opt.available ? "" : " (unavailable)"}
                    </option>
                  ))}
                </select>
              </label>
              {modelError && (
                <span className="dashboard-composer__model-error" role="alert">
                  {modelError}
                </span>
              )}
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
                <span>{guestSession ? "Send" : "Ask OPNXT"}</span>
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
        {(guestSession || guestMessages.length > 0 || guestError || chatNotice) && (
          <div style={{ marginTop: 20 }} aria-live="polite" aria-label="Ask OPNXT conversation">
            {guestError && (
              <div className="dashboard-status dashboard-status--error" role="alert">
                {guestError}
              </div>
            )}
            {deepLinkError && !guestError && (
              <div className="dashboard-status dashboard-status--error" role="alert">
                {deepLinkError}
              </div>
            )}
            {chatNotice && !guestError && !deepLinkError && (
              <div className="dashboard-status" role="status">
                {chatNotice}
              </div>
            )}
            <div
              style={{
                display: "grid",
                gap: 12,
                marginTop: 12,
                maxHeight: 320,
                overflowY: "auto",
                padding: 12,
                borderRadius: 12,
                border: "1px solid var(--border, #e0e0e0)",
                background: "var(--surface, #f8f9fb)",
              }}
            >
              {guestMessages.map((msg) => (
                <div
                  key={msg.message_id}
                  style={{
                    background: msg.role === "assistant" ? "#fff" : "var(--base, #edf2ff)",
                    borderRadius: 10,
                    padding: "10px 12px",
                    boxShadow: "var(--shadow-sm, 0 1px 2px rgba(15, 23, 42, 0.08))",
                  }}
                >
                  <strong>{msg.role === "assistant" ? "Assistant" : "You"}</strong>
                  <div style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{msg.content}</div>
                </div>
              ))}
              <div ref={askBottomRef} />
            </div>
            {guestSession && (
              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
                <button
                  type="button"
                  className="dashboard-composer__link"
                  onClick={() => {
                    resetAskExperience();
                    setDraft("");
                    requestAnimationFrame(() => composerRef.current?.focus());
                  }}
                >
                  Start a new Ask OPNXT
                </button>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
