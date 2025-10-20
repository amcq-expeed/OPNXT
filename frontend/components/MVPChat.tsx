import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChatModelOption,
  ChatMessage,
  createChatSession,
  listChatMessages,
  listChatModels,
  postChatMessage,
  putProjectContext,
  aiGenerateDocuments,
  generateDocuments,
  saveLeanSnapshot,
  listDocumentVersions,
  getDocumentVersion,
  DocumentVersionsResponse,
} from "../lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { initializeApp, getApps } from "firebase/app";
import styles from "./MVPChat.module.css";
import {
  getAuth,
  onAuthStateChanged,
  signInAnonymously,
  signOut,
  User as FirebaseUser,
} from "firebase/auth";
import {
  getModelPreference,
  setModelPreference,
} from "../lib/modelPreference";

function defaultFirebaseConfig(): Record<string, string> | null {
  if (typeof window !== "undefined") {
    try {
      const raw = (window as any).__OPNXT_FIREBASE__ as
        | Record<string, string>
        | undefined;
      if (raw) return raw;
    } catch {}
  }
  const {
    NEXT_PUBLIC_FIREBASE_API_KEY,
    NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
    NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  } = process.env as Record<string, string | undefined>;
  if (!NEXT_PUBLIC_FIREBASE_API_KEY) return null;
  return {
    apiKey: NEXT_PUBLIC_FIREBASE_API_KEY,
    authDomain: NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN || "",
    projectId: NEXT_PUBLIC_FIREBASE_PROJECT_ID || "",
  };
}

type DocumentGenerationResult = {
  projectId: string;
  mode: "docs" | "snapshot";
};

interface MVPChatProps {
  projectId: string;
  onDocumentsGenerated?: (result: DocumentGenerationResult) => void;
  onOpenDocuments?: () => void;
  docCount?: number;
  initialPrompt?: string;
  onUpgradeRequested?: () => Promise<{
    token: string;
    user: { uid: string };
  } | null>;
  onMigrationRequested?: (payload: {
    projectId: string;
    guestUserId: string;
    permanentToken: string;
  }) => Promise<void>;
  firebaseConfig?: Record<string, unknown>;
}

export default function MVPChat({
  projectId,
  onDocumentsGenerated,
  onOpenDocuments,
  docCount = 0,
  initialPrompt,
  onUpgradeRequested,
  onMigrationRequested,
  firebaseConfig,
}: MVPChatProps) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState<string>("");
  const [sending, setSending] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [generating, setGenerating] = useState<boolean>(false);
  const [assistantTyping, setAssistantTyping] = useState<boolean>(false);
  const [generationStages, setGenerationStages] = useState<string[]>([]);
  const [toast, setToast] = useState<{
    type: "error" | "info";
    message: string;
    actionLabel?: string;
    action?: () => void;
  } | null>(null);
  const [generationProgress, setGenerationProgress] = useState<number>(0);
  const [authUser, setAuthUser] = useState<FirebaseUser | null>(null);
  const [authReady, setAuthReady] = useState<boolean>(false);
  const [showPaywallModal, setShowPaywallModal] = useState<boolean>(false);
  const [interceptedApprove, setInterceptedApprove] = useState<string | null>(
    null,
  );
  const [migrationPending, setMigrationPending] = useState<boolean>(false);
  const [hasDocs, setHasDocs] = useState<boolean>(docCount > 0);

  const bottomRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const snapshotRef = useRef<string | null>(null);

  useEffect(() => {
    if (docCount > 0) {
      setHasDocs(true);
    }
  }, [docCount]);

  // Simple in-chat documents viewer state
  const [docsOpen, setDocsOpen] = useState<boolean>(false);
  const [docVersions, setDocVersions] =
    useState<DocumentVersionsResponse | null>(null);
  const [docLoading, setDocLoading] = useState<boolean>(false);
  const [docError, setDocError] = useState<string | null>(null);
  const [docFile, setDocFile] = useState<string>("");
  const [docVer, setDocVer] = useState<number | null>(null);
  const [docContent, setDocContent] = useState<string>("");
  const [modelOptions, setModelOptions] = useState<ChatModelOption[]>([]);
  const [modelLoading, setModelLoading] = useState<boolean>(false);
  const [modelError, setModelError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>("adaptive:auto");

  const serializeModelKey = (opt: ChatModelOption) => `${opt.provider}:${opt.model}`;

  const loadDoc = useCallback(
    async (fname: string, version: number) => {
      try {
        setDocLoading(true);
        setDocError(null);
        const dv = await getDocumentVersion(projectId, fname, version);
        setDocFile(dv.filename);
        setDocVer(dv.version);
        setDocContent(dv.content);
      } catch (e: any) {
        setDocError(e?.message || String(e));
      } finally {
        setDocLoading(false);
      }
    },
    [projectId],
  );

  const openDocsDrawer = useCallback(async () => {
    try {
      setDocsOpen(true);
      setDocLoading(true);
      setDocError(null);
      const v = await listDocumentVersions(projectId);
      setDocVersions(v);
      const files = Object.keys(v.versions || {});
      if (files.length > 0) {
        setHasDocs(true);
      }
      if (files.length > 0) {
        const first = files[0];
        const list = v.versions[first] || [];
        const latest = list.length ? list[list.length - 1].version : undefined;
        if (typeof latest === "number") {
          await loadDoc(first, latest);
        }
      } else if (snapshotRef.current) {
        setDocFile("Lean Snapshot (unsaved)");
        setDocVer(null);
        setDocContent(snapshotRef.current);
        setHasDocs(true);
      } else {
        setDocContent("");
      }
    } catch (e: any) {
      setDocError(e?.message || String(e));
    } finally {
      setDocLoading(false);
    }
  }, [projectId, loadDoc]);

  const pushGenerationStage = (label: string, progress?: number) => {
    setGenerationStages((prev) => [...prev, label]);
    if (typeof progress === "number") {
      setGenerationProgress(Math.max(0, Math.min(1, progress)));
    }
  };

  useEffect(() => {
    // Auto-scroll when messages change
    try {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    } catch {}
  }, [messages.length]);

  // On mount, focus composer and bring it into view so user doesn't need to scroll first
  useEffect(() => {
    const t = setTimeout(() => {
      try {
        textareaRef.current?.focus();
        textareaRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      } catch {}
    }, 0);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (typeof initialPrompt !== "string") return;
    setDraft(initialPrompt);
  }, [initialPrompt]);

  useEffect(() => {
    let cancelled = false;
    setModelLoading(true);
    setModelError(null);
    listChatModels()
      .then((items) => {
        if (cancelled) return;
        const filtered = Array.isArray(items)
          ? items.filter((opt) => !opt.provider.startsWith("search"))
          : [];
        setModelOptions(filtered);
        const persisted = getModelPreference();
        if (persisted) {
          const match = filtered.find(
            (opt) =>
              opt.provider === persisted.provider &&
              opt.model === persisted.model,
          );
          if (match) {
            setSelectedModel(serializeModelKey(match));
          } else if (persisted.provider === "adaptive") {
            setSelectedModel("adaptive:auto");
          }
        } else if (filtered.length > 0) {
          setSelectedModel(serializeModelKey(filtered[0]));
        }
      })
      .catch((error: any) => {
        if (cancelled) return;
        setModelError(
          error?.message || "Unable to load available models right now.",
        );
      })
      .finally(() => {
        if (!cancelled) setModelLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const cfg = firebaseConfig || defaultFirebaseConfig();
    if (!cfg || !cfg.apiKey) {
      if (process.env.NODE_ENV !== "production") {
        console.warn(
          "Firebase config missing; MVP chat will run without auth.",
        );
      }
      setAuthReady(true);
      return;
    }
    if (!getApps().length) {
      initializeApp(cfg as any);
    }
    const auth = getAuth();
    const unsub = onAuthStateChanged(
      auth,
      async (user: FirebaseUser | null) => {
        if (user) {
          setAuthUser(user);
          setAuthReady(true);
          return;
        }
        try {
          const anon = await signInAnonymously(auth);
          setAuthUser(anon.user);
        } catch (err) {
          if (process.env.NODE_ENV !== "production") {
            console.error("Anonymous sign-in failed", err);
          }
          setAuthUser(null);
        } finally {
          setAuthReady(true);
        }
      },
    );
    return () => unsub();
  }, [firebaseConfig]);

  async function ensureSession(): Promise<string> {
    if (sessionId) return sessionId;
    const created = await createChatSession(projectId, "MVP Chat");
    setSessionId(created.session_id);
    return created.session_id;
  }

  async function refreshMessages(sid: string) {
    try {
      const msgs = await listChatMessages(sid);
      setMessages(msgs);
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  }

  async function onNewChat() {
    if (!projectId) return;
    try {
      setError(null);
      setNotice(null);
      const created = await createChatSession(projectId, "MVP Chat");
      setSessionId(created.session_id);
      setMessages([]);
      setDraft("");
      requestAnimationFrame(() =>
        bottomRef.current?.scrollIntoView({ behavior: "smooth" }),
      );
      setNotice("Started a new chat.");
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  }

  async function sendChatMessage(text: string) {
    if (!text.trim()) return;
    try {
      setSending(true);
      setAssistantTyping(true);
      setError(null);
      const sid = await ensureSession();
      const now = new Date().toISOString();
      setMessages((prev) =>
        prev.concat([
          {
            message_id: "local-" + Math.random().toString(36).slice(2),
            session_id: sid,
            role: "user",
            content: text,
            created_at: now,
          },
        ] as any),
      );
      const [providerOverride, modelOverride] = (() => {
        if (!selectedModel) return [null, null];
        const [provider, ...rest] = selectedModel.split(":");
        const model = rest.join(":") || null;
        if (!provider || provider === "adaptive") {
          return [null, null];
        }
        return [provider, model];
      })();
      await postChatMessage(sid, text, {
        provider: providerOverride,
        model: modelOverride,
      });
      const msgs = await listChatMessages(sid);
      setMessages(msgs);
      setNotice("Assistant replied.");
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setSending(false);
      setAssistantTyping(false);
    }
  }

  async function onSend(e?: React.FormEvent) {
    if (e) e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    if (shouldInterceptApproval(text)) {
      interceptApproval(text);
      return;
    }
    await sendChatMessage(text);
    setDraft("");
  }

  const shouldInterceptApproval = (text: string) => {
    const normalized = text.trim().toLowerCase();
    if (!normalized) return false;
    const keywords = ["approve", "baseline", "baselining complete"];
    return keywords.some(
      (kw) => normalized === kw || normalized.startsWith(kw + " "),
    );
  };

  const interceptApproval = (text: string) => {
    if (!authUser || authUser.isAnonymous) {
      setInterceptedApprove(text);
      setShowPaywallModal(true);
      return;
    }
    void finalizeApproval(text);
  };

  const finalizeApproval = async (text: string) => {
    await sendChatMessage(text);
    setDraft("");
    setInterceptedApprove(null);
  };

  const handleUpgrade = async () => {
    if (!onUpgradeRequested) {
      setShowPaywallModal(false);
      return;
    }
    try {
      setMigrationPending(true);
      const auth = getAuth();
      const current = auth.currentUser;
      const guestUid = current?.uid || authUser?.uid || "";
      if (!guestUid) throw new Error("Guest session not established");
      const result = await onUpgradeRequested();
      if (!result) {
        setMigrationPending(false);
        return;
      }
      const { token } = result;
      // Migration handshake
      if (onMigrationRequested) {
        await onMigrationRequested({
          projectId,
          guestUserId: guestUid,
          permanentToken: token,
        });
      }
      setShowPaywallModal(false);
      setMigrationPending(false);
      if (interceptedApprove) {
        await finalizeApproval(interceptedApprove);
      }
    } catch (err: any) {
      setMigrationPending(false);
      const msg = err?.message || "Upgrade failed. Please try again.";
      setToast({ type: "error", message: msg });
    }
  };

  const handleCancelUpgrade = () => {
    setShowPaywallModal(false);
    setInterceptedApprove(null);
  };

  // --- Extract canonical SHALL requirements from chat ---
  const extractedShalls = useMemo(() => {
    const texts = messages.map((m) => m.content).join("\n");
    return extractShallFromText(texts);
  }, [messages]);

  // --- Readiness heuristic for enabling Generate Docs (scored, conversational-first) ---
  const readiness = useMemo(() => {
    const base = computeReadiness(messages, extractedShalls);
    const minUserMsgs = messages.filter((m) => m.role === "user").length >= 3;
    const minShalls = extractedShalls.length >= 3;
    const minTokens = messages.reduce(
      (total, m) => total + (m.content?.split(/\s+/).length || 0),
      0,
    );
    const ready = base.ready && minUserMsgs && minShalls && minTokens >= 120;
    const missing = new Set(base.missing);
    if (!minUserMsgs) missing.add("discovery depth (at least 3 user inputs)");
    if (!minShalls) missing.add("minimum 3 canonical requirements");
    if (minTokens < 120) missing.add("detailed context (120+ words)");
    return {
      ...base,
      ready,
      missing: Array.from(missing),
      reason: ready
        ? `Ready (score ${base.score}).`
        : `Need more detail before generating. Coverage score ${base.score}%.`,
    };
  }, [messages, extractedShalls]);
  // Compact UX: hide readiness panel by default (no SHALL messaging in UI)
  const showReadiness = false;

  // Notify once when readiness flips from false -> true
  const wasReadyRef = useRef<boolean>(false);
  useEffect(() => {
    if (readiness.ready && !wasReadyRef.current) {
      setToast({
        type: "info",
        message:
          "Enough detail captured. Generate a Lean Snapshot now or continue refining for full docs.",
      });
    }
    wasReadyRef.current = readiness.ready;
  }, [readiness.ready]);

  const targetBacklogCount = useMemo(() => {
    const totalChars = messages.reduce(
      (n, m) => n + (m.content?.length || 0),
      0,
    );
    const base = Math.max(4, reqsCount(extractedShalls) * 2);
    const depth = Math.floor(totalChars / 350); // more chat -> more backlog
    const estimate = base + depth * 3;
    return Math.max(6, Math.min(estimate, 40)); // clamp to 6..40
  }, [messages, extractedShalls]);

  function reqsCount(arr: string[]) {
    return Array.isArray(arr) ? arr.length : 0;
  }

  function buildPromptFromConversation(
    reqs: string[],
    msgs: ChatMessage[],
    targetStories = targetBacklogCount,
  ): string {
    // Limit transcript for prompt budget
    const recent = msgs.slice(-25);
    const transcript = recent
      .map((m) => `${m.role === "user" ? "User" : "Assistant"}: ${m.content}`)
      .join("\n");
    const reqBlock = reqs.length
      ? `Detected Canonical Requirements (SHALL):\n- ${reqs.join("\n- ")}`
      : "No explicit SHALL items detected; infer from transcript.";
    return [
      "You are an SDLC documentation generator. Produce COMPLETE, PRODUCTION-READY artifacts for this initiative based ONLY on the information below.",
      "",
      "Deliverables (all required):",
      "- Project Charter (problem, objectives, scope, stakeholders, constraints, success metrics)",
      "- Software Requirements Specification (SRS) with FR/NFR, use cases, assumptions, constraints, glossary",
      "- Software Design Document (SDD) with high-level architecture, components, data model, integration points",
      "- Test Plan with strategy, test types, entry/exit, environments, traceability matrix mapping to requirements",
      "",
      "Guidelines:",
      "- Be specific and self-consistent; avoid placeholders.",
      "- Ground every section in the transcript and requirements; add reasonable assumptions if gaps exist.",
      "- Treat the 'Detected Canonical Requirements (SHALL)' as the authoritative list: include them in the SRS and ensure traceability into SDD and Test Plan.",
      "",
      reqBlock,
      "Conversation Transcript (most recent first within this window):",
      transcript,
    ].join("\n\n");
  }

  async function onGenerateDocs(forceSnapshot = false) {
    if (!projectId) return;
    try {
      setGenerating(true);
      setError(null);
      setNotice("Applying requirements to Stored Context…");
      setGenerationStages([]);
      setGenerationProgress(0);
      pushGenerationStage("Applying requirements to Stored Context…", 0.25);
      setToast(null);
      // 1) Persist ONLY the current session's requirements (overwrite to avoid stale context)
      const payload = {
        data: { summaries: {}, answers: { Requirements: extractedShalls } },
      } as any;
      await putProjectContext(projectId, payload);

      // 2) Build prompt directly from the live conversation + detected requirements
      const prompt = buildPromptFromConversation(extractedShalls, messages);
      const runSnapshot = forceSnapshot || !readiness.ready;
      if (runSnapshot) {
        setNotice("Summarizing discovery findings…");
        pushGenerationStage("Preparing Lean Idea Validation Snapshot…", 0.65);
        const priorMessageCount = messages.length;
        const snapshot = buildLeanSnapshot(
          messages,
          extractedShalls,
          readiness,
        );
        const now = new Date().toISOString();
        // Append snapshot as assistant message for immediate feedback
        setMessages((prev) =>
          prev.concat([
            {
              message_id: "snapshot-" + Math.random().toString(36).slice(2),
              session_id: sessionId || "snapshot",
              role: "assistant",
              content: snapshot,
              created_at: now,
            } as any,
          ]),
        );

        try {
          pushGenerationStage("Saving snapshot to project context…", 0.85);
          await saveLeanSnapshot(projectId, {
            markdown_content: snapshot,
            metadata: {
              source: "mvp_chat",
              generated_at: now,
              message_count_before_snapshot: priorMessageCount,
              extracted_shalls: extractedShalls.length,
              readiness: {
                ready: readiness.ready,
                score: readiness.score,
                reason: readiness.reason,
                missing: readiness.missing,
              },
            },
          });
          setNotice(
            "Lean Idea Validation Snapshot saved. Capture more detail when you want the full SDLC bundle.",
          );
          pushGenerationStage("Snapshot saved.", 1);
          snapshotRef.current = snapshot;
          setHasDocs(true);
          setToast({
            type: "info",
            message: "Snapshot saved. View now?",
            actionLabel: "Open",
            action: () => {
              setToast(null);
              void openDocsDrawer();
            },
          });
          try {
            onDocumentsGenerated &&
              onDocumentsGenerated({ projectId, mode: "snapshot" });
          } catch {}
        } catch (err: any) {
          if (process.env.NODE_ENV !== "production") {
            console.error("Failed to persist Lean Snapshot", err);
          }
          setNotice(
            "Snapshot ready locally. Saving to project context failed.",
          );
          pushGenerationStage("Snapshot ready (not saved).", 1);
          setToast({
            type: "error",
            message:
              "Snapshot stored in chat, but persisting to project context failed. Try again later or copy the snapshot manually.",
          });
          snapshotRef.current = snapshot;
          setHasDocs(true);
          setToast({
            type: "info",
            message: "Snapshot ready. View now?",
            actionLabel: "Open",
            action: () => {
              setToast(null);
              void openDocsDrawer();
            },
          });
          try {
            onDocumentsGenerated &&
              onDocumentsGenerated({ projectId, mode: "snapshot" });
          } catch {}
        }
      } else {
        setNotice("Generating documents via AI…");
        pushGenerationStage("Generating documents via AI…", 0.65);
        try {
          await aiGenerateDocuments(projectId, {
            input_text: prompt,
            include_backlog: true,
            doc_types: ["ProjectCharter", "SRS", "SDD", "TestPlan"],
          });
        } catch (e) {
          // Fallback to deterministic generator
          setNotice("AI unavailable, falling back to deterministic generator…");
          pushGenerationStage(
            "AI unavailable, falling back to deterministic generator…",
            0.8,
          );
          const paste = [
            "Requirements (SHALL):",
            extractedShalls.map((s) => "- " + s).join("\n"),
            "",
            "Conversation Transcript:",
            messages.map((m) => `${m.role}: ${m.content}`).join("\n"),
          ].join("\n");
          await generateDocuments(projectId, {
            traceability_overlay: true,
            paste_requirements: paste,
            answers: { Requirements: extractedShalls } as any,
            summaries: {},
          });
        }
        setNotice("Generation complete.");
        pushGenerationStage("Generation complete.", 1);
        setToast({
          type: "info",
          message: "Documents generated. View now?",
          actionLabel: "Open",
          action: () => {
            setToast(null);
            void openDocsDrawer();
          },
        });
        setHasDocs(true);
        try {
          onDocumentsGenerated &&
            onDocumentsGenerated({ projectId, mode: "docs" });
        } catch {}
      }
    } catch (e: any) {
      setError(e?.message || String(e));
      const msg = e?.message || "Generation failed. Please try again.";
      pushGenerationStage(`Generation failed: ${msg}`);
      setGenerationProgress(0);
      setToast({
        type: "error",
        message: msg,
        actionLabel: "Retry",
        action: () => {
          setToast(null);
          onGenerateDocs();
        },
      });
    } finally {
      setGenerating(false);
      setTimeout(() => {
        setGenerationStages([]);
        setGenerationProgress(0);
      }, 4000);
    }
  }

  const readinessScore = Math.round(readiness.score || 0);
  const readinessPercent = Math.max(0, Math.min(100, readinessScore));
  const subtitle =
    messages.length === 0
      ? "Share what you’re building, who it serves, and any constraints."
      : readiness.ready
        ? "Charter-ready. Review your notes, then generate the full PMO package when you’re confident."
        : "Discovery mode. Capture problem, audience, evidence, and blockers. Save a Lean Snapshot anytime for next steps.";
  const handleToastDismiss = () => setToast(null);
  const handleToastAction = () => {
    if (!toast || !toast.action) return;
    const action = toast.action;
    setToast(null);
    action();
  };

  return (
    <div className={"mvp-chat " + styles.chat}>
      {/* Subtitle hidden for compact ChatGPT-like layout */}

      <div
        className={`mvp-chat__history ${styles.history}`}
        role="log"
        aria-live="polite"
        aria-label="Conversation"
      >
        {messages.length === 0 ? (
          <div className={`mvp-chat__empty ${styles.empty}`}>
            <p>
              Describe your initiative, the teams or stakeholders involved,
              critical features, and any constraints like timelines or
              compliance. Mention integrations, data needs, or non-functional
              requirements so the assistant can shape stronger documentation.
            </p>
          </div>
        ) : (
          <ul className={`mvp-chat__messages ${styles.messages}`}>
            {messages.map((m) => (
              <li
                key={m.message_id}
                className={`msg-row ${m.role === "user" ? "msg-row--user" : "msg-row--assistant"}`}
              >
                <div
                  className={`msg ${m.role === "user" ? "msg-user" : "msg-assistant"} ${styles.msg} ${m.role === "user" ? styles.msgUser : styles.msgAssistant}`}
                  aria-label={`${m.role} message`}
                >
                  {m.content}
                  <div
                    className="msg-meta"
                    style={{ textAlign: m.role === "user" ? "right" : "left" }}
                  >
                    {new Date(m.created_at).toLocaleTimeString()}
                  </div>
                </div>
              </li>
            ))}
            {assistantTyping && (
              <li className="msg-row msg-row--assistant">
                <div
                  className="msg msg-assistant"
                  aria-live="polite"
                  aria-label="assistant typing"
                >
                  <div className="typing-indicator" role="status">
                    <span className="typing-dots">
                      <span />
                      <span />
                      <span />
                    </span>
                    <span>Assistant is typing…</span>
                  </div>
                </div>
              </li>
            )}
          </ul>
        )}
        <div ref={bottomRef} />
      </div>

      <div className={`mvp-chat__composer ${styles.composer}`}>
        <form className={`mvp-chat__form ${styles.form}`} onSubmit={onSend}>
          <textarea
            className={`textarea chat-input mvp-chat__textarea ${styles.textarea}`}
            aria-label="Your message"
            placeholder="Describe your idea or requirement… (Enter to send, Shift+Enter for newline)"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSend();
              }
            }}
            disabled={!authReady || sending}
            ref={textareaRef}
            autoFocus
          />
          <div className={styles.modelSelectorRow}>
            <label className="muted" style={{ fontSize: 12 }}>
              Model
              <select
                className="select"
                value={selectedModel}
                onChange={(event) => {
                  const value = event.target.value;
                  setSelectedModel(value);
                  const choice = modelOptions.find(
                    (opt) => serializeModelKey(opt) === value,
                  );
                  if (choice) {
                    setModelPreference(choice.provider, choice.model);
                  } else if (value.startsWith("adaptive")) {
                    setModelPreference("adaptive", "auto");
                  }
                }}
                disabled={modelLoading || modelOptions.length === 0}
              >
                {modelOptions.map((opt) => (
                  <option
                    key={serializeModelKey(opt)}
                    value={serializeModelKey(opt)}
                    disabled={!opt.available && !opt.adaptive}
                  >
                    {opt.label}
                    {opt.available ? "" : " (unavailable)"}
                  </option>
                ))}
              </select>
            </label>
            {modelError && (
              <span className="muted" style={{ fontSize: 12 }} role="alert">
                {modelError}
              </span>
            )}
          </div>
          <button
            type="submit"
            className={`btn btn-primary mvp-chat__send ${styles.send}`}
            disabled={!authReady || sending || !draft.trim()}
            aria-busy={sending || !authReady}
          >
            {sending ? "Sending…" : "Send"}
          </button>
        </form>

        <div className={`mvp-chat__meta ${styles.meta}`}>
          {!readiness.ready ? (
            <div className={`mvp-chat__actions ${styles.actions}`}>
              <button
                className="btn btn-primary"
                type="button"
                disabled
                aria-disabled="true"
              >
                Capture more detail to unlock docs
              </button>
              <span className="muted" style={{ fontSize: 12 }}>
                {readiness.reason}
              </span>
            </div>
          ) : (
            <div className={`mvp-chat__actions ${styles.actions}`}>
              <button
                className="btn btn-primary"
                onClick={() => onGenerateDocs()}
                aria-busy={generating}
              >
                {generating ? "Generating…" : "Generate Docs"}
              </button>
            </div>
          )}
        </div>

        {hasDocs && (
          <div className="mvp-chat__actions" style={{ marginTop: 4 }}>
            <button
              type="button"
              className="btn"
              onClick={() => openDocsDrawer()}
            >
              Open documents
            </button>
          </div>
        )}
      </div>

      {toast && (
        <div className="toast-stack" role="status" aria-live="polite">
          <div className={`toast toast-${toast.type}`}>
            <span className="grow">{toast.message}</span>
            {toast.actionLabel && toast.action && (
              <button type="button" onClick={handleToastAction}>
                {toast.actionLabel}
              </button>
            )}
            <button
              type="button"
              className="toast-dismiss"
              onClick={handleToastDismiss}
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {showPaywallModal && (
        <div className="modal-backdrop" role="presentation">
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="paywall-title"
          >
            <div className="modal-header">
              <h3 id="paywall-title">Baseline PD-001</h3>
              <button
                type="button"
                className="modal-close"
                onClick={handleCancelUpgrade}
                aria-label="Close"
              >
                ×
              </button>
            </div>
            <div className="modal-body">
              <p>
                To baseline PD-001 and preserve this project, please sign in or
                start your free trial.
              </p>
              <p className="muted">
                Your captured requirements, snapshots, and documents will
                migrate to your new workspace automatically once you upgrade.
              </p>
            </div>
            <div
              className="modal-footer"
              style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}
            >
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleCancelUpgrade}
                disabled={migrationPending}
              >
                Not now
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleUpgrade}
                disabled={migrationPending}
                aria-busy={migrationPending}
              >
                {migrationPending ? "Preparing…" : "Sign In / Start Free Trial"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* In-chat Documents Viewer Drawer */}
      {docsOpen && (
        <div
          className={`drawer open`}
          role="dialog"
          aria-modal="true"
          aria-label="Generated documents"
        >
          <div
            className="drawer__backdrop"
            onClick={() => setDocsOpen(false)}
          />
          <div className="drawer__panel">
            <div className="drawer__header">
              <strong>Documents</strong>
              <button
                type="button"
                className="btn"
                onClick={() => setDocsOpen(false)}
                aria-label="Close"
              >
                ×
              </button>
            </div>
            <div
              className="drawer__body mvp-doc-drawer"
              style={{ display: "grid", gap: 12 }}
            >
              {docError && (
                <div className="error" role="alert">
                  {docError}
                </div>
              )}
              {!docVersions && !snapshotRef.current && !docLoading && (
                <div className="muted">No documents yet.</div>
              )}
              {docVersions && (
                <div
                  style={{
                    display: "flex",
                    gap: 8,
                    alignItems: "center",
                    flexWrap: "wrap",
                  }}
                >
                  <label>
                    File
                    <select
                      className="select"
                      value={docFile}
                      onChange={(e) => {
                        const fname = e.target.value;
                        setDocFile(fname);
                        const list = docVersions.versions[fname] || [];
                        const v = list.length
                          ? list[list.length - 1].version
                          : 1;
                        void loadDoc(fname, v);
                      }}
                    >
                      {Object.keys(docVersions.versions).map((f) => (
                        <option key={f} value={f}>
                          {f}
                        </option>
                      ))}
                    </select>
                  </label>
                  {docFile && docVersions.versions[docFile] && (
                    <label>
                      Version
                      <select
                        className="select"
                        value={String(docVer ?? "")}
                        onChange={(e) => {
                          const v = Number(e.target.value);
                          setDocVer(v);
                          void loadDoc(docFile, v);
                        }}
                      >
                        {docVersions.versions[docFile].map((info) => (
                          <option key={info.version} value={info.version}>
                            v{info.version}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <a
                    className="btn"
                    href={
                      docFile
                        ? `/projects/${encodeURIComponent(projectId)}?tab=Docs&file=${encodeURIComponent(docFile)}${docVer ? `&version=${docVer}` : ""}`
                        : "#"
                    }
                  >
                    Open in Workspace
                  </a>
                </div>
              )}
              {docLoading && (
                <div className="badge" role="status">
                  Loading…
                </div>
              )}
              {!docLoading && docContent && (
                <div
                  style={{
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    padding: 12,
                    background: "#fff",
                    color: "#111",
                  }}
                >
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {docContent}
                  </ReactMarkdown>
                </div>
              )}
              {!docVersions && snapshotRef.current && !docContent && (
                <div
                  style={{
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    padding: 12,
                    background: "#fff",
                    color: "#111",
                  }}
                >
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {snapshotRef.current}
                  </ReactMarkdown>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Detected Requirements panel intentionally hidden for MVP-clean UI */}
    </div>
  );
}

function buildLeanSnapshot(
  messages: ChatMessage[],
  shalls: string[],
  readiness: {
    ready: boolean;
    reason: string;
    score: number;
    missing: string[];
  },
): string {
  const userMessages = messages.filter((m) => m.role === "user");
  const latestUser = userMessages.length
    ? userMessages[userMessages.length - 1].content.trim()
    : "";
  const firstUser = userMessages.length ? userMessages[0].content.trim() : "";
  const conceptSource = latestUser || firstUser;
  const conceptSummary = conceptSource
    ? conceptSource
        .split(/\n+/)
        .map((s) => s.trim())
        .filter(Boolean)
        .slice(0, 2)
        .join(" ")
    : "Idea still forming — capture the problem, audience, and envisioned solution.";

  const userText = userMessages
    .map((m) => (m.content || "").toLowerCase())
    .join(" ");
  const signals: string[] = [];
  if (/(interview|customer discovery|user research|survey)/.test(userText)) {
    signals.push("Customer discovery activities referenced.");
  }
  if (/(waitlist|signup|beta|pilot|demo|prototype|poc)/.test(userText)) {
    signals.push("Early adoption signal (waitlist/beta/prototype) mentioned.");
  }
  if (/(revenue|pricing|paid|contract|invoice|subscription)/.test(userText)) {
    signals.push("Monetisation evidence or pricing exploration noted.");
  }
  if (/(partner|integration|loi|memorandum|channel)/.test(userText)) {
    signals.push("Partnership or integration interest highlighted.");
  }
  if (!signals.length) {
    signals.push(
      "No validation signals captured yet. Focus on interviews, signups, or prototype feedback.",
    );
  }

  const missingKeys = Array.isArray(readiness.missing) ? readiness.missing : [];
  const unknownMap: Record<string, string> = {
    "stakeholders/users":
      "Stakeholders, personas, or buyers not clearly identified.",
    "scope/objectives":
      "Value proposition, success metrics, or boundaries remain unclear.",
    "NFRs (performance/security)":
      "Non-functional expectations (e.g., performance, security, compliance) still unknown.",
    "constraints/risks": "Constraints, risks, or assumptions not documented.",
    "UI/API/integrations":
      "Interfaces, integrations, or touchpoints not described yet.",
    "testing/acceptance":
      "Acceptance criteria or validation tests not articulated.",
    "data model/retention":
      "Data flows, retention, or schema considerations missing.",
    "clear requirements (SHALL)":
      "Concrete requirements not yet articulated as SHALL statements.",
  };
  const criticalUnknowns = missingKeys.map(
    (m) => unknownMap[m] || `${m} still needs clarification.`,
  );
  if (!criticalUnknowns.length) {
    criticalUnknowns.push(
      "Key uncertainties resolved — ready to formalize when you choose.",
    );
  }

  const experimentTemplates: Record<
    string,
    { experiment: string; goal: string; owner: string; timeframe: string }
  > = {
    "stakeholders/users": {
      experiment: "Stakeholder interviews (5 conversations)",
      goal: "Validate primary personas and pains",
      owner: "Founder / Product Lead",
      timeframe: "1-2 weeks",
    },
    "scope/objectives": {
      experiment: "Success metrics workshop",
      goal: "Quantify KPIs and MVP boundaries",
      owner: "Product + Sponsor",
      timeframe: "1 week",
    },
    "NFRs (performance/security)": {
      experiment: "NFR & compliance spike",
      goal: "Document performance/security baselines",
      owner: "Tech Lead / Security",
      timeframe: "1 week",
    },
    "constraints/risks": {
      experiment: "Risk and constraint mapping",
      goal: "Surface budget, timeline, and regulatory concerns",
      owner: "Project Sponsor",
      timeframe: "1 week",
    },
    "UI/API/integrations": {
      experiment: "Integration touchpoint sketching",
      goal: "Outline key interfaces and data exchanges",
      owner: "Product + Engineering",
      timeframe: "1 week",
    },
    "testing/acceptance": {
      experiment: "Acceptance criteria drafting session",
      goal: "Define how success will be validated",
      owner: "QA / Product",
      timeframe: "3-5 days",
    },
    "data model/retention": {
      experiment: "Data model whiteboarding",
      goal: "Clarify entities, retention, and compliance needs",
      owner: "Engineering",
      timeframe: "1 week",
    },
    "clear requirements (SHALL)": {
      experiment: "Requirement refinement workshop",
      goal: "Draft 5-7 canonical SHALL statements",
      owner: "Product + Engineering",
      timeframe: "3-5 days",
    },
  };

  const experiments = missingKeys
    .map((key) => experimentTemplates[key])
    .filter(Boolean) as {
    experiment: string;
    goal: string;
    owner: string;
    timeframe: string;
  }[];
  if (!experiments.length) {
    experiments.push(
      {
        experiment: "Customer validation interviews",
        goal: "Validate problem urgency and willingness to pay",
        owner: "Founder / Product Lead",
        timeframe: "1-2 weeks",
      },
      {
        experiment: "MVP scope checkpoint",
        goal: "Agree on top 3 capabilities and success metrics",
        owner: "Product + Sponsor",
        timeframe: "1 week",
      },
    );
  }

  const checklistItems = [
    { label: "Executive sponsor identified", key: "stakeholders/users" },
    { label: "Top 3 capabilities prioritised", key: "scope/objectives" },
    { label: "Success metrics (KPIs) defined", key: "scope/objectives" },
    { label: "Constraints / risks documented", key: "constraints/risks" },
    {
      label: "Non-functional requirements captured",
      key: "NFRs (performance/security)",
    },
    {
      label: "Compliance / privacy considerations assessed",
      key: "NFRs (performance/security)",
    },
    { label: "Acceptance / test strategy outlined", key: "testing/acceptance" },
  ];
  const missingSet = new Set(missingKeys);
  const readinessChecklist = checklistItems.map(
    (item) => `${missingSet.has(item.key) ? "- [ ]" : "- [x]"} ${item.label}`,
  );

  const requirementsBlock = shalls.length
    ? ["## Detected Requirements (SHALL)", ...shalls.map((s) => `- ${s}`)].join(
        "\n",
      )
    : "";

  const nowIso = new Date().toISOString();

  return [
    "# Lean Idea Validation Snapshot",
    `Generated: ${nowIso}`,
    "",
    "## Concept Summary",
    conceptSummary,
    "",
    "## Validation Signals",
    signals.map((s) => `- ${s}`).join("\n"),
    "",
    "## Critical Unknowns",
    criticalUnknowns.map((u) => `- ${u}`).join("\n"),
    "",
    "## Recommended Next Experiments",
    "| Experiment | Goal | Owner | Timeframe |",
    "| --- | --- | --- | --- |",
    experiments
      .map(
        (e) => `| ${e.experiment} | ${e.goal} | ${e.owner} | ${e.timeframe} |`,
      )
      .join("\n"),
    "",
    "## Readiness Checklist",
    readinessChecklist.join("\n"),
    "",
    requirementsBlock,
  ]
    .filter(Boolean)
    .join("\n");
}

function extractShallFromText(text: string): string[] {
  const out: string[] = [];
  const lines = text.split(/\r?\n/);
  for (const ln of lines) {
    const cleanedLine = ln
      .trim()
      .replace(/^[-*•\d.\)\s]+/, "")
      .trim();
    if (!cleanedLine) continue;
    const sentences = cleanedLine
      .split(/(?<=[.!?])\s+|\s*;\s+|(?<!\w)\s*-\s+(?=\w)/)
      .map((s) => s.trim())
      .filter(Boolean);
    for (let s of sentences) {
      let t = s.trim();
      if (t.length < 6) continue;
      if (/^(note|summary|context)[:\s]/i.test(t)) continue;

      // Handle "As a ..., I want to ..." style
      const asMatch = t.match(
        /^As\s+a[n]?\s+[^,]+,\s*I\s+want\s+to\s+(.+?)(?:\s+so\s+that.*)?$/i,
      );
      if (asMatch) {
        t = asMatch[1].trim();
      }

      // Strip subjects + modals (the system|system|we|it) + (shall|should|must|will|needs to|need to)
      const modal = t.match(
        /^(?:the\s+system|system|we|it)\s+(?:shall|should|must|will|needs?\s+to|need\s+to)\s+(.*)$/i,
      );
      if (modal) {
        t = modal[1].trim();
      }

      // Remove leading infinitive markers
      t = t.replace(/^(?:to\s+|be\s+able\s+to\s+)/i, "");

      // If sentence already uses SHALL, normalize and keep
      if (/\bshall\b/i.test(s)) {
        let keep = s.replace(/^the\s+system\s+shall/i, "The system SHALL");
        if (!/[.!?]$/.test(keep)) keep += ".";
        out.push(keep);
        continue;
      }

      // Otherwise, construct canonical SHALL
      if (!/[.!?]$/.test(t)) t += ".";
      const clause = t.charAt(0).toUpperCase() + t.slice(1);
      let composed = `The system SHALL ${clause}`;
      composed = composed.replace(
        /^The system SHALL\s+(?:The\s+system\s+shall\s+)/i,
        "The system SHALL ",
      );
      out.push(composed);
    }
  }
  const seen = new Set<string>();
  const uniq: string[] = [];
  for (const r of out) {
    const rr = r.trim();
    if (rr && !seen.has(rr)) {
      seen.add(rr);
      uniq.push(rr);
    }
  }
  return uniq;
}

function computeReadiness(
  messages: ChatMessage[],
  shalls: string[],
): { ready: boolean; reason: string; score: number; missing: string[] } {
  const userCount = messages.filter((m) => m.role === "user").length;
  const totalChars = messages.reduce((n, m) => n + (m.content?.length || 0), 0);
  const allText = messages.map((m) => m.content).join("\n");
  const hasStakeholders =
    /(stakeholder|user(?:s)?|persona|customer|admin|operator)/i.test(allText);
  const hasScope = /(scope|objective|goal|outcome|success|kpi|metric)/i.test(
    allText,
  );
  const hasNFR =
    /(nfr|non[- ]?functional|performance|latency|throughput|availability|reliability|security|compliance|gdpr|hipaa)/i.test(
      allText,
    );
  const hasConstraints =
    /(constraint|assumption|risk|limitation|budget|timeline|deadline)/i.test(
      allText,
    );
  const hasInterface =
    /(\bui\b|ux|screen|page|api|endpoint|integration|webhook)/i.test(allText);
  const hasTesting = /(test|qa|acceptance\s*criteria|traceability)/i.test(
    allText,
  );
  const hasData =
    /(data\s*model|schema|database|storage|retention|index)/i.test(allText);
  // Q&A loop detection
  let qaLoop = false;
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === "assistant" && /\?/.test(m.content || "")) {
      qaLoop = messages
        .slice(i + 1)
        .some(
          (x) => x.role === "user" && (x.content || "").trim().length >= 20,
        );
      break;
    }
  }
  let score = 0;
  const missing: string[] = [];
  if (shalls.length >= 5) score += 25;
  else if (shalls.length >= 3) score += 20;
  else if (shalls.length >= 1) score += 10;
  else missing.push("clear requirements (SHALL)");
  if (hasStakeholders) score += 15;
  else missing.push("stakeholders/users");
  if (hasScope) score += 15;
  else missing.push("scope/objectives");
  if (hasNFR) score += 10;
  else missing.push("NFRs (performance/security)");
  if (hasConstraints) score += 10;
  else missing.push("constraints/risks");
  if (hasInterface) score += 10;
  else missing.push("UI/API/integrations");
  if (hasTesting) score += 5;
  else missing.push("testing/acceptance");
  if (hasData) score += 5;
  else missing.push("data model/retention");
  if (userCount >= 2) score += 10;
  if (userCount >= 3) score += 10;
  if (totalChars >= 400) score += 10;
  if (qaLoop) score += 10;
  if (score > 100) score = 100;
  const ready = score >= 60;
  const reason = ready
    ? `Ready (score ${score}).`
    : `Readiness ${score}%. Keep chatting to cover gaps.`;
  return { ready, reason, score, missing };
}
