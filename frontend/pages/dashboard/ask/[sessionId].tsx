import Link from "next/link";
import { useRouter } from "next/router";
import type { FormEvent } from "react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import ChatComposer from "../../../components/chat/ChatComposer";
import MarkdownMessage from "../../../components/MarkdownMessage";
import {
  ChatMessage,
  ChatModelOption,
  ChatSession,
  getChatSession,
  listChatMessages,
  listChatModels,
  postChatMessage,
  trackEvent,
} from "../../../lib/api";
import { getModelPreference, setModelPreference } from "../../../lib/modelPreference";
import { useUserContext } from "../../../lib/user-context";

function resolveKeyFromQuery(
  filtered: ChatModelOption[],
  providerParam: string | null,
  modelParam: string | null,
): string {
  if (!providerParam) {
    return "adaptive";
  }
  if (providerParam === "adaptive") {
    return "adaptive";
  }
  if (modelParam) {
    const key = `${providerParam}:${modelParam}`;
    const match = filtered.find((opt) => `${opt.provider}:${opt.model}` === key);
    if (match) return key;
  }
  const fallback = filtered.find((opt) => opt.provider === providerParam);
  if (fallback) {
    return `${fallback.provider}:${fallback.model}`;
  }
  return "adaptive";
}

export default function AskWorkspacePage() {
  const router = useRouter();
  const { persona } = useUserContext();
  const sessionId =
    typeof router.query.sessionId === "string" ? router.query.sessionId : null;
  const providerParam =
    typeof router.query.provider === "string" ? router.query.provider : null;
  const modelParam =
    typeof router.query.model === "string" ? router.query.model : null;
  const prefillParam =
    typeof router.query.prefill === "string" ? router.query.prefill : null;
  const sourceParam =
    typeof router.query.source === "string" ? router.query.source : "unknown";

  const [session, setSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [sending, setSending] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [draft, setDraft] = useState<string>("");
  const [modelOptions, setModelOptions] = useState<ChatModelOption[]>([]);
  const [modelLoading, setModelLoading] = useState<boolean>(false);
  const [modelError, setModelError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>("adaptive");
  const [extendedThinking, setExtendedThinking] = useState<boolean>(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState<boolean>(false);
  const [statusNotice, setStatusNotice] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const prefillAppliedRef = useRef<boolean>(false);
  const prefillGhostAppliedRef = useRef<boolean>(false);
  const autosendAppliedRef = useRef<boolean>(false);

  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const max = 200;
    el.style.height = `${Math.min(el.scrollHeight, max)}px`;
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

  const heroTitle = useMemo(() => session?.title || "Ask OPNXT", [session]);
  const assistantLabel = useMemo(() => session?.title || "Ask OPNXT assistant", [session]);
  const assistantInitials = useMemo(() => {
    const label = assistantLabel.trim();
    if (!label) return "AO";
    const initials = label
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("");
    return initials || "AO";
  }, [assistantLabel]);

  const ensurePrefillVisible = useCallback(
    (list: ChatMessage[], sid?: string | null) => {
      if (!prefillParam) return list;
      const trimmed = prefillParam.trim();
      const hasRealUserPrefill = list.some(
        (msg) =>
          msg.role === "user" &&
          msg.message_id !== "prefill-draft" &&
          msg.content.trim() === trimmed,
      );
      if (hasRealUserPrefill) {
        prefillGhostAppliedRef.current = false;
        return list;
      }
      if (!prefillGhostAppliedRef.current) return list;
      const hasGhost = list.some((msg) => msg.message_id === "prefill-draft");
      if (hasGhost) return list;
      return list.concat({
        message_id: "prefill-draft",
        session_id: sid ?? session?.session_id ?? "local",
        role: "user",
        content: prefillParam,
        created_at: new Date().toISOString(),
      });
    },
    [prefillParam, session?.session_id],
  );

  useEffect(() => {
    prefillGhostAppliedRef.current = Boolean(prefillParam);
  }, [prefillParam]);

  useEffect(() => {
    setMessages((prev) => ensurePrefillVisible(prev, session?.session_id));
  }, [ensurePrefillVisible, session?.session_id]);

  useEffect(() => {
    setModelLoading(true);
    setModelError(null);
    listChatModels()
      .then((options) => {
        const filtered = Array.isArray(options)
          ? options.filter((opt) => !opt.provider.startsWith("search"))
          : [];
        setModelOptions(filtered);
        const persisted = getModelPreference();
        let initial = "adaptive";
        if (providerParam) {
          initial = resolveKeyFromQuery(filtered, providerParam, modelParam);
        } else if (persisted) {
          if (persisted.provider === "adaptive") {
            initial = "adaptive";
          } else {
            const match = filtered.find(
              (opt) =>
                opt.provider === persisted.provider && opt.model === persisted.model,
            );
            if (match) {
              initial = `${match.provider}:${match.model}`;
            }
          }
        }
        setSelectedModel(initial);
      })
      .catch((err: any) => {
        setModelError(err?.message || "Unable to load model catalog right now.");
      })
      .finally(() => {
        setModelLoading(false);
      });
  }, [providerParam, modelParam]);

  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    setNotice("Loading conversation…");
    getChatSession(sessionId)
      .then((payload) => {
        const nextSession = payload?.session;
        const initialMessages = payload?.messages || [];
        if (!nextSession) {
          throw new Error("Session not found");
        }
        setSession(nextSession);
        const hydrated = ensurePrefillVisible(initialMessages, nextSession.session_id);
        setMessages(hydrated);
        setNotice(null);
        trackEvent("ask_workspace_loaded", {
          sessionId,
          source: sourceParam,
          persona: persona ?? null,
        });
      })
      .catch((err: any) => {
        const detail = err?.message || "Unable to load this chat session.";
        setError(detail);
        setNotice(null);
        trackEvent("ask_workspace_load_failed", {
          sessionId,
          source: sourceParam,
          message: detail,
        });
      })
      .finally(() => {
        setLoading(false);
      });
  }, [sessionId, sourceParam, persona, ensurePrefillVisible]);

  useEffect(() => {
    if (!prefillParam || prefillAppliedRef.current) return;
    setDraft(prefillParam);
    prefillAppliedRef.current = true;
    requestAnimationFrame(() => {
      autoResize();
      textareaRef.current?.focus();
    });
  }, [prefillParam, autoResize]);

  useEffect(() => {
    if (!messages.length) return;
    requestAnimationFrame(() => {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    });
  }, [messages.length]);

  const handleSubmit = useCallback(
    async (event?: FormEvent<HTMLFormElement>) => {
      event?.preventDefault();
      const message = draft.trim();
      if (!message || !session) return;
      const { provider, model } = resolveModelOverrides();
      setSending(true);
      setError(null);
      setNotice("Waiting for assistant response…");
      setStatusNotice("Assistant is thinking…");
      const optimistic: ChatMessage = {
        message_id: `local-${Date.now()}`,
        session_id: session.session_id,
        role: "user",
        content: message,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) =>
        prev
          .filter((msg) => msg.message_id !== "prefill-draft")
          .concat(optimistic),
      );
      setDraft("");
      requestAnimationFrame(autoResize);
      try {
        await postChatMessage(session.session_id, message, {
          provider: provider ?? undefined,
          model: model ?? undefined,
        });
        trackEvent("ask_workspace_message_sent", {
          sessionId: session.session_id,
          provider: provider ?? "adaptive",
          source: sourceParam,
        });
        const latest = await listChatMessages(session.session_id);
        const hydrated = ensurePrefillVisible(latest ?? [], session.session_id);
        setMessages(hydrated);
        setNotice(null);
        setStatusNotice(null);
      } catch (err: any) {
        const detail = err?.message || "Unable to send message right now.";
        setError(detail);
        setNotice(null);
        setStatusNotice(null);
        setMessages((prev) =>
          ensurePrefillVisible(
            prev.filter((msg) => msg.message_id !== optimistic.message_id),
            session.session_id,
          ),
        );
        setDraft(message);
        requestAnimationFrame(autoResize);
      } finally {
        setSending(false);
      }
    },
    [draft, session, resolveModelOverrides, sourceParam, autoResize, ensurePrefillVisible],
  );

  useEffect(() => {
    const autosend = router.query.autosend === "1";
    if (!autosend || autosendAppliedRef.current) return;
    if (!session || !prefillParam) return;
    autosendAppliedRef.current = true;
    void handleSubmit();
  }, [router.query.autosend, session, prefillParam, handleSubmit]);

  const composerPlaceholder = session
    ? "Continue the conversation…"
    : "Preparing workspace…";

  const emptyStateCopy = "Ask a question or share an update to get the conversation started.";

  return (
    <div className="accelerator-shell ask-workspace-shell" aria-live="polite">
      <header className="accelerator-header">
        <nav className="accelerator-breadcrumb" aria-label="Breadcrumb">
          <Link href="/dashboard">Workspace</Link>
          <span aria-hidden="true">/</span>
          <span>Ask OPNXT</span>
        </nav>
        <h1>{heroTitle}</h1>
        <p className="accelerator-subhead">
          Launch a focused Ask OPNXT conversation just like a quick-start accelerator. Your session stays available so you can pick up where you left off.
        </p>
      </header>

      {notice && !error ? (
        <div className="accelerator-status" role="status">
          {notice}
        </div>
      ) : null}
      {statusNotice && !error ? (
        <div className="accelerator-status" role="status">
          {statusNotice}
        </div>
      ) : null}
      {loading && !session ? (
        <div className="accelerator-status" role="status">
          Loading conversation…
        </div>
      ) : null}
      {error ? (
        <div className="accelerator-status accelerator-status--error" role="alert">
          {error}
        </div>
      ) : null}

      <main className="accelerator-main ask-workspace-main">
        <section className="accelerator-chat ask-workspace-chat" aria-label="Ask OPNXT conversation">
          {!loading && messages.length === 0 ? (
            <div className="accelerator-status accelerator-status--muted">{emptyStateCopy}</div>
          ) : null}
          {messages.length > 0 && (
            <ol className="accelerator-messages">
              {messages.map((msg) => {
                const isAssistant = msg.role === "assistant";
                const roleLabel = msg.role === "system" ? "System" : isAssistant ? assistantLabel : "You";
                return (
                  <li
                    key={msg.message_id}
                    className={`accelerator-message accelerator-message--${msg.role}`}
                  >
                    <span className="accelerator-message__role">
                      {isAssistant ? (
                        <>
                          <span aria-hidden="true" className="accelerator-message__avatar">
                            {assistantInitials}
                          </span>
                          {roleLabel}
                        </>
                      ) : (
                        roleLabel
                      )}
                    </span>
                    <div className="accelerator-message__bubble">
                      <MarkdownMessage>{msg.content}</MarkdownMessage>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
          <div ref={bottomRef} />
        </section>
      </main>

      <ChatComposer
        className="accelerator-composer ask-workspace-composer"
        draft={draft}
        onDraftChange={setDraft}
        onDraftInput={() => requestAnimationFrame(autoResize)}
        onSubmit={(event) => {
          void handleSubmit(event);
        }}
        sending={sending}
        sendDisabled={sending || loading || !draft.trim()}
        textareaDisabled={sending || loading || !session}
        hasSession={Boolean(session)}
        textareaId="ask-workspace-input"
        textareaRef={textareaRef}
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
          const match = modelOptions.find((opt) => `${opt.provider}:${opt.model}` === value);
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
    </div>
  );
}
