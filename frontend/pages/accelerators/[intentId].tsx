import Link from "next/link";
import { useRouter } from "next/router";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  LaunchAcceleratorResponse,
  getAcceleratorSession,
  launchAcceleratorSession,
  postAcceleratorMessage,
  promoteAcceleratorSession,
  trackEvent,
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
  }, [router.isReady, intentId, sessionId, persona, source]);

  const session = data?.session;
  const intent = data?.intent;
  const messages = data?.messages ?? [];
  const personaLabel = useMemo(() => formatPersonaLabel(session?.persona), [session?.persona]);

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

  async function refreshSession(id: string) {
    try {
      const fresh = await getAcceleratorSession(id);
      setData(fresh);
      setPromotionProjectId(fresh.session.project_id ?? null);
    } catch (e: any) {
      setError(e?.message || "Unable to refresh session.");
    }
  }

  async function handleSend(event?: FormEvent) {
    event?.preventDefault();
    if (!session || sending) return;
    const content = draft.trim();
    if (!content) return;
    setDraft("");
    setSending(true);
    setError(null);

    try {
      trackEvent("accelerator_prompt_sent", {
        sessionId: session.session_id,
        intentId: intent?.intent_id,
        length: content.length,
      });
      await postAcceleratorMessage(session.session_id, content);
      await refreshSession(session.session_id);
    } catch (e: any) {
      setError(e?.message || "Unable to send message right now.");
      setDraft(content);
    } finally {
      setSending(false);
    }
  }

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
