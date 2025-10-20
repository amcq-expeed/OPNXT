import Link from "next/link";
import { useRouter } from "next/router";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  LaunchAcceleratorResponse,
  getAcceleratorSession,
  launchAcceleratorSession,
  postAcceleratorMessage,
  promoteAcceleratorSession,
  trackEvent,
  API_BASE_URL,
  getAccessToken,
} from "../../lib/api";
import { useUserContext } from "../../lib/user-context";
import MarkdownMessage from "../../components/MarkdownMessage";

const PERSONA_LABELS: Record<string, string> = {
  architect: "Solution Architect",
  engineer: "Engineering Lead",
  product: "Product Manager",
  pm: "Project Manager",
  analyst: "Business Analyst",
  approver: "Governance Approver",
  auditor: "Compliance Auditor",
  qa: "Quality Assurance",
  developer: "Developer",
  executive: "Executive Sponsor",
  operations: "Operations",
  people: "People / HR",
};

type SimplifiedArtifact = { filename: string; created_at?: string; version?: number; summary?: string };

type SuggestedPrompt = { id: string; label: string; body: string };

function formatPersonaLabel(code: string | null | undefined): string | null {
  if (!code) return null;
  const normalized = code.toLowerCase();
  return PERSONA_LABELS[normalized] ?? code.replace(/(^|_|-)([a-z])/g, (_, __, chr) => chr.toUpperCase());
}

export default function AcceleratorChatPage() {
  const router = useRouter();
  const { user, persona } = useUserContext();
  const [data, setData] = useState<LaunchAcceleratorResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<string>("");
  const [sending, setSending] = useState<boolean>(false);
  const [promoting, setPromoting] = useState<boolean>(false);
  const [promotionError, setPromotionError] = useState<string | null>(null);
  const [promotionProjectId, setPromotionProjectId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const [liveArtifacts, setLiveArtifacts] = useState<SimplifiedArtifact[]>([]);

  const intentId = useMemo(() => {
    const raw = router.query.intentId;
    return typeof raw === "string" ? raw : null;
  }, [router.query.intentId]);

  const sessionId = useMemo(() => {
    const raw = router.query.session;
    return typeof raw === "string" ? raw : null;
  }, [router.query.session]);

  const source = useMemo(() => {
    const raw = router.query.source;
    return typeof raw === "string" && raw ? raw : "dashboard";
  }, [router.query.source]);

  useEffect(() => {
    if (!router.isReady || !intentId) return;
    let cancelled = false;

    const resolvedIntentId = intentId as string;

    async function hydrate() {
      setLoading(true);
      setError(null);
      try {
        let result: LaunchAcceleratorResponse;
        if (sessionId) {
          result = await getAcceleratorSession(sessionId);
        } else {
          result = await launchAcceleratorSession(resolvedIntentId);
          const nextQuery: Record<string, string> = {
            intentId: resolvedIntentId,
            session: result.session.session_id,
          };
          if (source) nextQuery.source = source;
          void router.replace(
            { pathname: "/accelerators/[intentId]", query: nextQuery },
            undefined,
            { shallow: true },
          );
        }
        if (cancelled) return;
        setData(result);
        setPromotionProjectId(result.session.project_id ?? null);
        trackEvent("accelerator_session_opened", {
          intentId: result.intent.intent_id,
          persona: result.session.persona ?? null,
          source,
        });
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message || "Unable to start accelerator session.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    hydrate().catch(() => {
      if (cancelled) return;
      setLoading(false);
      setError("Unable to start accelerator session.");
    });

    return () => {
      cancelled = true;
    };
  }, [router, router.isReady, intentId, sessionId, source]);

  const session = data?.session;
  const intent = data?.intent;
  const messages = data?.messages ?? [];
  const personaLabel = useMemo(() => formatPersonaLabel(session?.persona), [session?.persona]);
  const normalizeArtifacts = useCallback((list: any): SimplifiedArtifact[] => {
    if (!Array.isArray(list)) return [];
    return list.map((item) => ({
      filename: String(item?.filename ?? ""),
      created_at: typeof item?.created_at === "string" ? item.created_at : undefined,
      version:
        typeof item?.meta?.version === "number"
          ? item.meta.version
          : typeof item?.meta?.version === "string"
          ? Number(item.meta.version)
          : undefined,
      summary: typeof item?.meta?.summary === "string" ? item.meta.summary : undefined,
    }));
  }, []);

  const artifacts = useMemo(() => {
    const meta = session?.metadata;
    const list = (meta as any)?.artifacts;
    return normalizeArtifacts(list);
  }, [session?.metadata, normalizeArtifacts]);

  const suggestedPrompts = useMemo(() => {
    const meta = session?.metadata;
    const raw = (meta as any)?.suggested_prompts;
    if (!Array.isArray(raw)) return [] as SuggestedPrompt[];
    return raw
      .map((item, index) => ({
        id: String(item?.id ?? index),
        label: String(item?.label ?? `Prompt ${index + 1}`),
        body: String(item?.body ?? ""),
      }))
      .filter((prompt) => prompt.body.trim().length > 0);
  }, [session?.metadata]);

  const displayArtifacts = liveArtifacts.length ? liveArtifacts : artifacts;

  function formatAssistantPreview(content: string) {
    const lines = content.split(/\n+/).filter((line) => line.trim().length > 0);
    if (!lines.length) return content;
    const first = lines[0];
    const rest = lines.slice(1)
      .map((line) => {
        if (/^[\d\-•]/.test(line.trim())) {
          return `<li>${line.replace(/^[-•\d.)\s]+/, "").trim()}</li>`;
        }
        return `<p>${line}</p>`;
      })
      .join("");
    return `<strong>${first}</strong>${rest}`;
  }

  useEffect(() => {
    requestAnimationFrame(() => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }));
  }, [messages.length]);

  useEffect(() => {
    if (!session?.session_id) {
      setLiveArtifacts([]);
      return;
    }
    setLiveArtifacts(artifacts);
  }, [session?.session_id, artifacts]);

  useEffect(() => {
    if (!session?.session_id) return;
    let cancelled = false;
    const controller = new AbortController();

    const connect = async () => {
      const token = getAccessToken();
      try {
        const res = await fetch(
          `${API_BASE_URL}/accelerators/sessions/${session.session_id}/artifacts/stream`,
          {
            headers: token ? { Authorization: `Bearer ${token}` } : undefined,
            signal: controller.signal,
          },
        );
        if (!res.ok || !res.body) return;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!cancelled) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let boundary = buffer.indexOf("\n\n");
          while (boundary !== -1) {
            const chunk = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            const dataLine = chunk
              .split("\n")
              .map((line) => line.trim())
              .find((line) => line.startsWith("data:"));
            if (dataLine) {
              const payloadRaw = dataLine.replace(/^data:\s*/, "");
              if (payloadRaw) {
                try {
                  const payload = JSON.parse(payloadRaw);
                  const nextArtifacts = normalizeArtifacts(payload?.artifacts ?? []);
                  setLiveArtifacts(nextArtifacts);
                } catch (err) {
                  console.error("Failed to parse artifact stream", err);
                }
              }
            }
            boundary = buffer.indexOf("\n\n");
          }
        }
      } catch (err) {
        if (!cancelled) {
          console.error("Artifact stream error", err);
        }
      }
    };

    void connect();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [session?.session_id, normalizeArtifacts]);

  async function refreshSession(id: string) {
    try {
      const fresh = await getAcceleratorSession(id);
      setData(fresh);
      setPromotionProjectId(fresh.session.project_id ?? null);
    } catch (e: any) {
      setError(e?.message || "Unable to refresh session.");
    }
  }

  async function handleSend(event?: FormEvent, override?: string) {
    event?.preventDefault();
    if (!session || sending) return;
    const content = (override ?? draft).trim();
    if (!content) return;
    const messageToSend = content;
    if (!override) {
      setDraft("");
    }
    setSending(true);
    setError(null);

    try {
      trackEvent("accelerator_prompt_sent", {
        sessionId: session.session_id,
        intentId: intent?.intent_id,
        length: content.length,
      });
      await postAcceleratorMessage(session.session_id, content);
      void refreshSession(session.session_id);
    } catch (e: any) {
      setError(e?.message || "Unable to send message right now.");
      if (!override) {
        setDraft(messageToSend);
      }
    } finally {
      setSending(false);
    }
  }

  const handleQuickPrompt = useCallback(
    (prompt: SuggestedPrompt) => {
      if (!prompt?.body || !session || sending) return;
      trackEvent("accelerator_prompt_prefill", {
        sessionId: session.session_id,
        intentId: intent?.intent_id,
        promptId: prompt.id,
      });
      void handleSend(undefined, prompt.body);
    },
    [intent?.intent_id, session, sending],
  );

  async function handlePromote() {
    if (!session || !intent) return;
    setPromoting(true);
    setPromotionError(null);
    try {
      const result = await promoteAcceleratorSession(session.session_id, {
        name: intent.title,
        description: intent.description,
      });
      setPromotionProjectId(result.project_id);
      trackEvent("accelerator_session_promoted", {
        sessionId: session.session_id,
        intentId: intent.intent_id,
      });
    } catch (e: any) {
      setPromotionError(e?.message || "Unable to promote this session yet.");
    } finally {
      setPromoting(false);
    }
  }

  return (
    <div className="accelerator-shell">
      <header className="accelerator-header">
        <nav className="accelerator-breadcrumb" aria-label="Breadcrumb">
          <Link href="/dashboard">Workspace</Link>
          <span aria-hidden="true">/</span>
          <span>{intent?.title ?? "Accelerator"}</span>
        </nav>
        <h1>{intent?.title ?? "Accelerator chat"}</h1>
        {intent && <p className="accelerator-subhead">{intent.description}</p>}
        <div className="accelerator-meta" role="list">
          {intent?.requirement_area && (
            <span role="listitem">Focus: {intent.requirement_area}</span>
          )}
          {personaLabel && <span role="listitem">Persona: {personaLabel}</span>}
        </div>
        {intent?.deliverables?.length ? (
          <div className="accelerator-deliverables" role="list">
            {intent.deliverables.map((item) => (
              <span key={item} role="listitem">
                {item}
              </span>
            ))}
          </div>
        ) : null}
        <div className="accelerator-actions">
          <button
            type="button"
            className="accelerator-promote"
            onClick={handlePromote}
            disabled={promoting || !session}
          >
            {promoting ? "Promoting…" : promotionProjectId ? "Promoted" : "Promote to project"}
          </button>
          {promotionProjectId && (
            <Link href={`/projects/${promotionProjectId}`} className="accelerator-link">
              Open workspace ↗
            </Link>
          )}
        </div>
        {promotionError && (
          <div className="accelerator-status accelerator-status--error" role="alert">
            {promotionError}
          </div>
        )}
      </header>

      {error && (
        <div className="accelerator-status accelerator-status--error" role="alert">
          {error}
        </div>
      )}

      <main className="accelerator-chat" aria-live="polite">
        <aside
          style={{
            border: "1px solid var(--border, #e0e0e0)",
            borderRadius: 12,
            padding: 16,
            marginBottom: 16,
            background: "var(--surface, #f8f9fb)",
          }}
          aria-label="Generated artifacts"
        >
          <h2 style={{ margin: 0, fontSize: "1rem" }}>Artifacts</h2>
          <p style={{ marginTop: 8, marginBottom: 12, color: "var(--muted, #5f6a84)", fontSize: "0.875rem" }}>
            {artifacts.length
              ? "Latest documents captured for this accelerator session."
              : "Documents will appear here once generated."}
          </p>
          {artifacts.length > 0 && (
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
              {displayArtifacts.map((artifact) => (
                <li
                  key={`${artifact.filename}-${artifact.version ?? "v"}`}
                  style={{
                    border: "1px solid var(--border, #e0e0e0)",
                    borderRadius: 10,
                    padding: "8px 12px",
                    background: "#fff",
                    display: "grid",
                    gap: 6,
                  }}
                >
                  <div style={{ fontWeight: 600 }}>{artifact.filename || "Untitled"}</div>
                  <div style={{ fontSize: "0.8rem", color: "var(--muted, #5f6a84)" }}>
                    {artifact.version ? `Version ${artifact.version}` : null}
                    {artifact.version && artifact.created_at ? " • " : ""}
                    {artifact.created_at ? new Date(artifact.created_at).toLocaleString() : null}
                  </div>
                  {artifact.summary ? (
                    <div
                      style={{
                        fontSize: "0.85rem",
                        color: "var(--text, #27324b)",
                        background: "#f5f7fb",
                        borderRadius: 6,
                        padding: "6px 8px",
                        lineHeight: 1.4,
                      }}
                    >
                      {artifact.summary}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </aside>
        {loading && !session && <div className="accelerator-status">Loading accelerator…</div>}
        {!loading && session && (
          <>
            <ol className="accelerator-messages">
              {messages.map((message) => (
                <li
                  key={message.message_id}
                  className={`accelerator-message accelerator-message--${message.role}`}
                >
                  <span className="accelerator-message__role">
                    {message.role === "assistant" ? intent?.title ?? "Assistant" : "You"}
                  </span>
                  <MarkdownMessage>{message.content}</MarkdownMessage>
                </li>
              ))}
            </ol>
            <div ref={messagesEndRef} />
          </>
        )}
      </main>

      <footer className="accelerator-composer">
        <form onSubmit={handleSend} className="accelerator-form">
          {suggestedPrompts.length > 0 && (
            <div
              className="accelerator-quick-prompts"
              role="group"
              aria-label="Suggested prompts"
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 8,
                marginBottom: 12,
              }}
            >
              {suggestedPrompts.map((prompt) => (
                <button
                  key={prompt.id}
                  type="button"
                  className="accelerator-quick-prompt"
                  onClick={() => handleQuickPrompt(prompt)}
                  disabled={sending || !session}
                  style={{
                    border: "1px solid var(--border, #d6dbe7)",
                    background: "#eef2ff",
                    color: "#3341a0",
                    borderRadius: 999,
                    padding: "6px 14px",
                    fontSize: "0.85rem",
                    fontWeight: 600,
                    cursor: "pointer",
                    transition: "background 0.2s ease, color 0.2s ease",
                    opacity: sending || !session ? 0.6 : 1,
                  }}
                  onMouseEnter={(event) => {
                    (event.currentTarget as HTMLButtonElement).style.background = "#dce4ff";
                  }}
                  onMouseLeave={(event) => {
                    (event.currentTarget as HTMLButtonElement).style.background = "#eef2ff";
                  }}
                >
                  {prompt.label}
                </button>
              ))}
            </div>
          )}
          <label className="sr-only" htmlFor="accelerator-input">
            Send a message
          </label>
          <textarea
            id="accelerator-input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Share context or ask for the next step…"
            rows={3}
            disabled={sending || loading || !session}
          />
          <div className="accelerator-compose-actions">
            <button type="submit" disabled={!draft.trim() || sending || !session}>
              {sending ? "Sending…" : "Send"}
            </button>
          </div>
        </form>
      </footer>
    </div>
  );
}
