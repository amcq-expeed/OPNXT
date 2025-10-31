import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";
import ChatComposer from "../components/chat/ChatComposer";
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
  // TILE 1: From Concept to Requirements
  {
    intentId: "requirements-baseline",
    title: "From Concept to Requirements",
    description: "Turn your idea into a scoped project with defined goals, requirements, and delivery plan.",
    prefill:
      "Welcome! I'm ready to turn your idea into a full engineering plan. As a **Senior Solutions Architect**, I need just a few details. In a sentence or two, please tell me: **What is the core problem your application solves, and who is the target user?** I will use this to automatically populate the entire **`SDLC_PLAN.md`** with requirements, success metrics, and a basic technology stack.",
    group: "End-to-End",
    icon: "🧭",
    deliverables: [],
  },
  // TILE 2: Auto-Generate SDLC Docs
  {
    intentId: "generate-sdlc-doc",
    title: "Auto-Generate SDLC Docs",
    description: "Instantly create SRS, test plans, or architecture docs from project context or a short chat.",
    prefill:
      "Let's formalize your project's blueprint. I can generate any core SDLC document (e.g., **Software Architecture Document, Data Schema, or Detailed Test Plan**). Which specific document do you need me to generate right now, and what existing project file (like your plan or requirements) should I reference to ensure it's accurate?",
    group: "SDLC Phase",
    icon: "📄",
    deliverables: [],
  },
  // TILE 3: Design & Build Guidance
  {
    intentId: "design-build-guidance",
    title: "Design & Build Guidance",
    description: "Get coding suggestions, design patterns, and test scaffolding tailored to your project.",
    prefill:
      "Time to build! As your **Pair Programmer**, I can accelerate a specific coding task. What specific feature (e.g., 'the user login component' or 'the API to save data') are you working on right now? Please mention the file name or component you need help with so I can provide the exact code or test scaffolding based on the approved design.",
    group: "SDLC Phase",
    icon: "🧑‍💻",
    deliverables: [],
  },
  // TILE 4: Enhance Existing Documentation
  {
    intentId: "enhance-documentation",
    title: "Enhance Existing Documentation",
    description: "Review and refine your current documents without starting over.",
    prefill:
      "Documentation is key to project health. I'm ready to review, refine, or update any existing document or code comment in your project. **Which file needs enhancement, and what is the specific change or improvement you want me to make (e.g., 'Add a risk analysis section,' or 'Simplify the explanation of the database schema')?**",
    group: "Maintenance",
    icon: "📝",
    deliverables: [],
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
  const [extendedThinking, setExtendedThinking] = useState<boolean>(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState<boolean>(false);
  const [guestSession, setGuestSession] = useState<ChatSession | null>(null);
  const [guestMessages, setGuestMessages] = useState<ChatMessage[]>([]);
  const [guestLoading, setGuestLoading] = useState<boolean>(false);
  const [guestSending, setGuestSending] = useState<boolean>(false);
  const [guestError, setGuestError] = useState<string | null>(null);
  const [chatNotice, setChatNotice] = useState<string | null>(null);
  const [deepLinkError, setDeepLinkError] = useState<string | null>(null);

  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const askBottomRef = useRef<HTMLDivElement | null>(null);
  const acceleratorSectionRef = useRef<HTMLDivElement | null>(null);

  const autoResize = useCallback(() => {
    const el = composerRef.current;
    if (!el) return;
    el.style.height = "auto";
    const max = 200;
    el.style.height = `${Math.min(el.scrollHeight, max)}px`;
  }, []);

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
  }, [router]);

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

  const handleSubmit = async (event?: FormEvent<HTMLFormElement>) => {
    event?.preventDefault();
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
        requestAnimationFrame(autoResize);
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
    requestAnimationFrame(autoResize);
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
      requestAnimationFrame(autoResize);
    } finally {
      setGuestSending(false);
      setChatNotice(null);
    }
  };

  useEffect(() => {
    if (!guestMessages.length) return;
    requestAnimationFrame(() => askBottomRef.current?.scrollIntoView({ behavior: "smooth" }));
  }, [guestMessages.length]);

  const composerPlaceholder = guestSession
    ? "Share an update with the assistant…"
    : "How can OPNXT help you today?";

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
        <section aria-label="Guided copilots" className="accelerator-grid" ref={acceleratorSectionRef}>
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
        <ChatComposer
          className="dashboard-composer__inner"
          draft={draft}
          onDraftChange={setDraft}
          onDraftInput={() => requestAnimationFrame(autoResize)}
          onSubmit={(event) => {
            void handleSubmit(event);
          }}
          sending={guestSending || guestLoading}
          sendDisabled={guestSending || guestLoading || !draft.trim()}
          textareaDisabled={guestSending || guestLoading}
          hasSession={Boolean(guestSession)}
          textareaId="dashboard-ask-input"
          textareaRef={composerRef}
          placeholder={composerPlaceholder}
          modelOptions={modelOptions}
          modelLoading={modelLoading}
          modelError={modelError}
          selectedModelKey={selectedModel}
          onModelChange={(value) => {
            setSelectedModel(value);
            if (value === "adaptive") {
              setModelPreference("adaptive", "auto");
              return;
            }
            const match = modelOptions.find(
              (opt) => `${opt.provider}:${opt.model}` === value,
            );
            if (match) {
              setModelPreference(match.provider, match.model);
            }
          }}
          onTextareaKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void handleSubmit();
            }
          }}
          resourceMenu={{
            headerLabel: "Quick starts",
            items: [
              ...quickStarts.map((idea) => ({
                id: idea.intentId || idea.title,
                label: idea.title,
                icon: idea.icon,
                onSelect: () => {
                  launchChat(idea.prefill);
                },
              })),
              {
                id: "browse-templates",
                label: "Browse templates",
                accessoryLabel: "→",
                onSelect: () => {
                  void router.push("/templates");
                },
              },
            ],
          }}
          connectorsMenu={{
            headerLabel: "Sources",
            toggles: [
              {
                id: "web-search",
                label: "Enable web search",
                icon: "🌐",
                value: webSearchEnabled,
                onChange: setWebSearchEnabled,
              },
            ],
          }}
          extendedThinking={{
            value: extendedThinking,
            onToggle: setExtendedThinking,
            icon: "🧠",
            tooltip: "Allow extended thinking",
          }}
          sendIcon={<span aria-hidden="true">↑</span>}
        />
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
