import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/router";
import ChatPanel from "../components/ChatPanel";
import {
  listProjects,
  createGuestChatSession,
  listChatMessages,
  postChatMessage,
  me,
  User,
  getAccessToken,
  Project,
  ChatSession,
  ChatMessage,
  GuestChatSessionResponse,
  generateDocuments,
  getProjectContext,
  aiGenerateDocuments,
} from "../lib/api";

export default function StartPage() {
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [autoLaunching, setAutoLaunching] = useState<boolean>(false);
  const [autoLaunchError, setAutoLaunchError] = useState<string | null>(null);
  const autoLaunchRef = useRef<boolean>(false);
  const [quickIdea, setQuickIdea] = useState<string>("");
  const [guestSession, setGuestSession] = useState<ChatSession | null>(null);
  const [guestMessages, setGuestMessages] = useState<ChatMessage[]>([]);
  const [guestLoading, setGuestLoading] = useState<boolean>(false);
  const [guestSending, setGuestSending] = useState<boolean>(false);
  const [guestError, setGuestError] = useState<string | null>(null);
  const [guestDraft, setGuestDraft] = useState<string>("");
  const guestBottomRef = useRef<HTMLDivElement | null>(null);

  // Use-existing state
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");

  async function refreshProjects() {
    try {
      setLoading(true);
      setError(null);
      const items = await listProjects();
      setProjects(items);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function onRegenerateFromStart() {
    if (!selectedProjectId) return;
    try {
      // Generate docs from the latest stored context, then take the user to Docs
      await generateDocuments(selectedProjectId, {
        traceability_overlay: true,
      });
      await router.push(
        `/projects/${encodeURIComponent(selectedProjectId)}?tab=Docs`,
      );
    } catch (e) {
      // non-blocking; show nothing special on start page
    }
  }

  function buildPromptFromContext(c: any): string {
    const data: any = c?.data || {};
    const planning = data?.summaries?.Planning || "";
    const reqs: string[] = Array.isArray(data?.answers?.Requirements)
      ? data.answers.Requirements
      : [];
    const parts = [
      planning ? `Planning Summary:\n${planning}` : "",
      reqs.length ? `Requirements:\n- ${reqs.join("\n- ")}` : "",
    ].filter(Boolean);
    if (parts.length) return parts.join("\n\n");
    return "Generate the standard documents (Project Charter, SRS, SDD, Test Plan) for this project based on current context.";
  }

  async function onAIGenerateFromStart() {
    if (!selectedProjectId) return;
    try {
      const latest = await getProjectContext(selectedProjectId);
      const prompt = buildPromptFromContext(latest);
      await aiGenerateDocuments(selectedProjectId, { input_text: prompt });
      await router.push(
        `/projects/${encodeURIComponent(selectedProjectId)}?tab=Docs`,
      );
    } catch (e) {
      // swallow for now; UI retains context
    }
  }

  const launchGuestChat = useCallback(
    async (prompt?: string) => {
      const initial = (prompt ?? quickIdea).trim();
      if (!initial) {
        setGuestError("Provide a quick-start idea to begin chatting.");
        return;
      }
      try {
        setGuestLoading(true);
        setAutoLaunchError(null);
        setGuestError(null);
        setNotice("Preparing Quick Start chat…");
        const sessionWithMessages: GuestChatSessionResponse = await createGuestChatSession({
          title: "Quick Start Chat",
          initial_message: initial,
        });
        setGuestSession(sessionWithMessages.session);
        setGuestMessages(sessionWithMessages.messages || []);
        setQuickIdea("");
        if (router.query.prefill) {
          void router.replace("/start", undefined, { shallow: true });
        }
      } catch (err: any) {
        const msg = err?.message || "Unable to launch quick start chat.";
        setGuestError(msg);
        setAutoLaunchError(msg);
        autoLaunchRef.current = false;
      } finally {
        setGuestLoading(false);
        setAutoLaunching(false);
        setNotice(null);
      }
    },
    [quickIdea, router],
  );

  useEffect(() => {
    if (typeof window !== "undefined" && !getAccessToken()) {
      const rt = encodeURIComponent("/start");
      window.location.href = `/login?returnTo=${rt}`;
      return;
    }
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const u = await me();
        setCurrentUser(u);
        await refreshProjects();
      } catch (e: any) {
        if (typeof window !== "undefined") {
          const rt = encodeURIComponent("/start");
          window.location.href = `/login?returnTo=${rt}`;
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!router.isReady) return;
    const q = router.query.prefill;
    const prefillRaw = typeof q === "string" ? q : "";
    if (!prefillRaw || autoLaunchRef.current) return;
    let decodedPrefill = prefillRaw;
    try {
      decodedPrefill = decodeURIComponent(prefillRaw);
    } catch {
      decodedPrefill = prefillRaw;
    }
    const normalizedPrefill = decodedPrefill.trim();
    if (!normalizedPrefill) return;
    autoLaunchRef.current = true;
    setAutoLaunching(true);
    void launchGuestChat(normalizedPrefill);
  }, [launchGuestChat, router.isReady, router.query.prefill]);

  useEffect(() => {
    if (!guestMessages.length) return;
    guestBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [guestMessages.length]);

  const handleGuestSend = useCallback(
    async (e?: React.FormEvent) => {
      if (e) e.preventDefault();
      if (!guestSession) return;
      const content = guestDraft.trim();
      if (!content || guestSending) return;
      const optimistic: ChatMessage = {
        message_id: `local-${Date.now()}`,
        session_id: guestSession.session_id,
        role: "user",
        content,
        created_at: new Date().toISOString(),
      };
      setGuestMessages((prev) => prev.concat(optimistic));
      setGuestDraft("");
      setGuestError(null);
      try {
        setGuestSending(true);
        await postChatMessage(guestSession.session_id, content);
        const latest = await listChatMessages(guestSession.session_id);
        setGuestMessages(latest ?? []);
      } catch (err: any) {
        const msg = err?.message || "Unable to send message.";
        setGuestError(msg);
        setGuestMessages((prev) => prev.filter((m) => m.message_id !== optimistic.message_id));
        setGuestDraft(content);
      } finally {
        setGuestSending(false);
      }
    },
    [guestDraft, guestSending, guestSession],
  );

  return (
    <div>
      <div className="section-title">Start</div>
      {loading && <div className="badge">Loading…</div>}
      {error && <p className="error">{error}</p>}
      {autoLaunchError && <p className="error">{autoLaunchError}</p>}
      {notice && <p className="notice">{notice}</p>}

      <div className="grid-2">
        {/* Quick Start */}
        <div className="card">
          <div className="section-title">Quick Start</div>
          <div style={{ display: "grid", gap: 12, maxWidth: 640, marginTop: 8 }}>
            <label>
              <span className="muted">Describe what you need help with</span>
              <textarea
                className="textarea"
                placeholder="Outline the idea or challenge to start a chat without creating a project."
                value={quickIdea}
                onChange={(e) => setQuickIdea(e.target.value)}
                rows={3}
              />
            </label>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button
                className="btn btn-primary"
                type="button"
                onClick={() => launchGuestChat()}
                disabled={guestLoading || autoLaunching}
              >
                {guestLoading || autoLaunching ? "Starting…" : "Start Quick Chat"}
              </button>
              {guestError && <span className="error" role="alert">{guestError}</span>}
            </div>
          </div>
          {guestSession ? (
            <div className="card" style={{ marginTop: 16 }}>
              <div className="section-title" style={{ marginBottom: 8 }}>
                Quick Start Chat
              </div>
              <div
                style={{
                  display: "grid",
                  gap: 8,
                  maxHeight: 360,
                  overflowY: "auto",
                  padding: 8,
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  background: "var(--surface)",
                }}
              >
                {guestMessages.map((msg) => (
                  <div
                    key={msg.message_id}
                    style={{
                      alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                      maxWidth: "80%",
                      background: msg.role === "user" ? "var(--primary-light)" : "#fff",
                      color: "var(--text)",
                      borderRadius: 12,
                      padding: "8px 12px",
                      boxShadow: "var(--shadow-sm)",
                    }}
                  >
                    <strong>{msg.role === "user" ? "You" : "Assistant"}</strong>
                    <div style={{ whiteSpace: "pre-wrap", marginTop: 4 }}>{msg.content}</div>
                  </div>
                ))}
                <div ref={guestBottomRef} />
              </div>
              <form
                onSubmit={handleGuestSend}
                style={{
                  display: "grid",
                  gap: 8,
                  marginTop: 12,
                }}
              >
                <label>
                  <span className="sr-only">Your message</span>
                  <textarea
                    className="textarea"
                    placeholder="Share more detail…"
                    value={guestDraft}
                    onChange={(e) => setGuestDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        void handleGuestSend();
                      }
                    }}
                    disabled={guestSending}
                    rows={3}
                  />
                </label>
                <div style={{ display: "flex", gap: 8, justifyContent: "space-between" }}>
                  <button
                    className="btn btn-primary"
                    type="submit"
                    disabled={guestSending || !guestDraft.trim()}
                  >
                    {guestSending ? "Sending…" : "Send"}
                  </button>
                  {guestError && <span className="error" role="alert">{guestError}</span>}
                </div>
              </form>
            </div>
          ) : (
            <div className="muted" style={{ marginTop: 16 }}>
              Start a quick guest chat to capture discovery notes without creating a project.
            </div>
          )}
        </div>

        {/* Use existing project */}
        <div className="card">
          <div className="section-title">Use Existing Project</div>
          <div
            style={{
              display: "flex",
              gap: 8,
              alignItems: "center",
              marginTop: 8,
              flexWrap: "wrap",
            }}
          >
            <select
              className="select"
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              aria-label="Select project"
            >
              <option value="">Choose a project…</option>
              {projects.map((p) => (
                <option key={p.project_id} value={p.project_id}>
                  {p.name} ({p.project_id})
                </option>
              ))}
            </select>
            {selectedProjectId && (
              <Link
                href={`/projects/${encodeURIComponent(selectedProjectId)}`}
                className="btn"
              >
                Open project details
              </Link>
            )}
          </div>
        </div>

        {/* Chat panel (full-width row) */}
        <div className="card" style={{ gridColumn: "1 / -1" }}>
          {selectedProjectId ? (
            <ChatPanel
              projectId={selectedProjectId}
              onAIGenerateRequested={onAIGenerateFromStart}
              onRegenerateRequested={onRegenerateFromStart}
              autoGenerateDefault={true}
            />
          ) : (
            <div className="muted">
              Select or create a project to start chatting.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
