import Link from "next/link";
import { useRouter } from "next/router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Project,
  DocGenResponse,
  getProject,
  generateDocuments,
  zipUrl,
  getProjectContext,
  putProjectContext,
  computeImpacts,
  ImpactResponse,
  ProjectContext,
  listDocumentVersions,
  getDocumentVersion,
  DocumentVersionsResponse,
  aiGenerateDocuments,
  orchestrateWorkflow,
  OrchestrateRequest,
  OrchestrateResponse,
  OrchestrateTimelineEntry,
  trackEvent,
  patchProjectDocument,
  DocumentEditRequest,
} from "../../lib/api";
import { useProjectDocumentStream } from "../../lib/useProjectDocumentStream";
import Tabs from "../../components/Tabs";
import ChatPanel from "../../components/ChatPanel";
import NextAction from "../../components/ui/NextAction";
import Stat from "../../components/ui/Stat";
import Stepper from "../../components/ui/Stepper";
import DocList from "../../components/DocList";
import Modal from "../../components/ui/Modal";

type WorkspaceScenario = {
  label: string;
  description: string;
  prompt: string;
};

export default function ProjectDetailsPage() {
  const router = useRouter();
  const id = typeof router.query.id === "string" ? router.query.id : "";

  const [project, setProject] = useState<Project | null>(null);
  const [docs, setDocs] = useState<DocGenResponse | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Auto-clear notices after a short delay and when tab changes
  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(null), 6000);
    return () => clearTimeout(t);
  }, [notice]);
  useEffect(() => {
    // Clear banner when switching tabs via query
    setNotice(null);
  }, [router.query.tab]);

  // Chat/Paste requirements UX state
  const [overlayOn, setOverlayOn] = useState<boolean>(false);
  const [docGeneration, setDocGeneration] = useState<{
    active: boolean;
    stage: "idle" | "context" | "llm" | "post";
    message?: string;
    model?: string;
    cancelRequested?: boolean;
  }>({ active: false, stage: "idle" });
  const [docGenerationLog, setDocGenerationLog] = useState<
    { timestamp: number; text: string }[]
  >([]);
  const resetDocGenerationLog = useCallback((text: string) => {
    setDocGenerationLog([{ timestamp: Date.now(), text }]);
  }, []);
  const appendDocLog = useCallback((text: string) => {
    setDocGenerationLog((prev) => {
      const next = [...prev, { timestamp: Date.now(), text }];
      return next.slice(-8);
    });
  }, []);

  // Design Q&A (Open Questions in SDD)
  const [designQuestions, setDesignQuestions] = useState<string[]>([]);
  const [designAnswers, setDesignAnswers] = useState<Record<number, string>>(
    {},
  );
  const [qaNotice, setQaNotice] = useState<string | null>(null);
  const [designGenerating, setDesignGenerating] = useState<boolean>(false);

  // Orchestration state
  const [orchestrating, setOrchestrating] = useState<boolean>(false);
  const [orchestrateError, setOrchestrateError] = useState<string | null>(null);
  const [orchestrateResult, setOrchestrateResult] =
    useState<OrchestrateResponse | null>(null);
  const [orchestrateTimeline, setOrchestrateTimeline] = useState<
    OrchestrateTimelineEntry[]
  >([]);

  // Stored Context state
  const [ctx, setCtx] = useState<ProjectContext | null>(null);
  const [ctxPlanning, setCtxPlanning] = useState<string>("");
  const [ctxRequirements, setCtxRequirements] = useState<string>("");
  const [savingCtx, setSavingCtx] = useState<boolean>(false);
  // Approvals (persisted in ctx.data.approvals)
  const [approvals, setApprovals] = useState<
    Record<string, { approved: boolean; approved_at?: string }>
  >({});
  const [approvalBusy, setApprovalBusy] = useState<boolean>(false);

  const {
    documents: streamedDocuments,
    documentMap: streamedDocumentMap,
    livePreview,
    status: streamStatus,
    heartbeatAt: streamHeartbeatAt,
    streaming: streamDraftActive,
    streamError,
    isConnected: streamConnected,
    reconnect: reconnectStream,
    recentUpdates,
  } = useProjectDocumentStream(
    id ? { projectId: id, autostart: Boolean(id) } : { projectId: null, autostart: false },
  );
  const [editMode, setEditMode] = useState(false);
  const [editDraft, setEditDraft] = useState("");
  const [editSummary, setEditSummary] = useState("");
  const [editSection, setEditSection] = useState("");
  const [editChangeDescription, setEditChangeDescription] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [lastSavedRevision, setLastSavedRevision] = useState<number | null>(null);
  const [heartbeatStale, setHeartbeatStale] = useState(false);
  const streamHeartbeatTimeoutMs = 20000;
  const lastStreamErrorRef = useRef<string | null>(null);
  const prevStreamConnectedRef = useRef<boolean | null>(null);

  useEffect(() => {
    if (!streamHeartbeatAt || typeof window === "undefined") {
      setHeartbeatStale(false);
      return;
    }
    setHeartbeatStale(Date.now() - streamHeartbeatAt > streamHeartbeatTimeoutMs);
    const timer = window.setInterval(() => {
      setHeartbeatStale(Date.now() - streamHeartbeatAt > streamHeartbeatTimeoutMs);
    }, Math.min(5000, streamHeartbeatTimeoutMs));
    return () => window.clearInterval(timer);
  }, [streamHeartbeatAt, streamHeartbeatTimeoutMs]);

  useEffect(() => {
    if (streamConnected) {
      setHeartbeatStale(false);
    }
  }, [streamConnected]);

  const buildOrchestrateGoal = useCallback(() => {
    const details: string[] = [];
    if (project?.name) details.push(`Project: ${project.name}`);
    if (ctxPlanning) details.push(`Planning Summary: ${ctxPlanning}`);
    if (ctxRequirements) {
      const lines = ctxRequirements
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);
      if (lines.length) {
        details.push(
          `Requirements:\n- ${lines
            .map((l) => l.replace(/^[-*]\s*/, ""))
            .join("\n- ")}`,
        );
      }
    }
    return details.length
      ? `Run multi-agent orchestration for this project.\n\n${details.join("\n\n")}`
      : "Run multi-agent orchestration for this project.";
  }, [project?.name, ctxPlanning, ctxRequirements]);

  const triggerOrchestration = useCallback(
    async (options?: OrchestrateRequest["options"]) => {
      if (!id) return;
      const goal = buildOrchestrateGoal();
      const payload: OrchestrateRequest = {
        goal,
        project_id: id,
        project_name: project?.name,
        options,
      };
      try {
        setOrchestrating(true);
        setOrchestrateError(null);
        setOrchestrateTimeline([]);
        const response = await orchestrateWorkflow(payload);
        setOrchestrateResult(response);
        setOrchestrateTimeline(response.timeline || []);
        setNotice("Orchestration completed successfully.");
        trackEvent("orchestration_run_completed", {
          projectId: id,
          runId: response.run_id,
        });
      } catch (error: any) {
        const msg =
          error?.message ||
          error?.detail ||
          "Unable to orchestrate workflow right now.";
        setOrchestrateError(msg);
        setNotice(null);
        trackEvent("orchestration_run_failed", {
          projectId: id,
          message: msg,
        });
      } finally {
        setOrchestrating(false);
      }
    },
    [id, buildOrchestrateGoal, project?.name],
  );

  // Impact analysis state
  const [frInput, setFrInput] = useState<string>("");
  const [impacts, setImpacts] = useState<ImpactResponse | null>(null);
  const [analyzing, setAnalyzing] = useState<boolean>(false);

  // Versioning state
  const [versions, setVersions] = useState<DocumentVersionsResponse | null>(
    null,
  );
  const [previewVersion, setPreviewVersion] = useState<{
    filename: string;
    version: number;
  } | null>(null);
  const [previewModalOpen, setPreviewModalOpen] = useState<boolean>(false);

  // AI generation options
  const [includeBacklog, setIncludeBacklog] = useState<boolean>(false);
  // Prefill for requirements chat quick-starts
  const [chipPrefill, setChipPrefill] = useState<string | undefined>(undefined);
  const prefillHandledRef = useRef<string | null>(null);
  const heroScenarios = useMemo<WorkspaceScenario[]>(
    () => [
      {
        label: "Healthcare",
        description: "Patient scheduling, telehealth and regulatory-ready journeys.",
        prompt:
          "Concept to Deployment scenario: Healthcare Appointment System. Confirm clinical and regulatory context, then drive requirements, architecture guidance, implementation steps, testing coverage, and deployment checklist. Produce Charter, SRS, SDD, and Test Plan when ready.",
      },
      {
        label: "Banking",
        description: "Payments, authentication, audit controls, and SLA reporting.",
        prompt:
          "Concept to Deployment scenario: Bank Payment Platform. Capture compliance constraints, then lead me through requirements, target architecture, implementation plan, testing, and deployment readiness with Charter, SRS, SDD, and Test Plan milestones.",
      },
      {
        label: "E-commerce",
        description: "Catalog, checkout, and fulfillment orchestration with analytics.",
        prompt:
          "Concept to Deployment scenario: E-commerce Store. Gather product, checkout, and fulfillment context, then outline requirements, architecture, implementation, testing, and deployment with Charter, SRS, SDD, and Test Plan outputs.",
      },
      {
        label: "Custom",
        description: "Bring your own initiative and tailor the SDLC workspace instantly.",
        prompt:
          "Concept to Deployment workspace kickoff. Ask for critical context, then guide me through requirements, architecture, implementation, testing, and deployment readiness. Produce Charter, SRS, SDD, and Test Plan as gates are satisfied.",
      },
    ],
    [],
  );

  const routeToTab = useCallback(
    (tab: string, prefill?: string) => {
      if (!id) return;
      if (prefill) {
        setChipPrefill(prefill);
      }
      void router.push({
        pathname: `/projects/${id}`,
        query: { tab },
      });
    },
    [id, router],
  );

  // Read ?prefill= from URL once to seed ChatPanel
  useEffect(() => {
    const rawPrefill =
      typeof router.query.prefill === "string"
        ? router.query.prefill
        : undefined;
    if (!rawPrefill) return;
    if (prefillHandledRef.current === rawPrefill) return;

    let decoded = rawPrefill;
    try {
      decoded = decodeURIComponent(rawPrefill);
    } catch {
      /* ignore decode errors; fall back to raw */
    }

    setChipPrefill(decoded);
    prefillHandledRef.current = rawPrefill;
  }, [router.query.prefill]);

  // Derived overview metrics
  const answers = useMemo(() => (ctx as any)?.data?.answers || {}, [ctx]);
  const reqCount = useMemo(
    () =>
      Array.isArray(answers?.Requirements) ? answers.Requirements.length : 0,
    [answers],
  );
  const charterApproved = !!approvals?.["ProjectCharter.md"]?.approved;
  const srsApproved = !!approvals?.["SRS.md"]?.approved;
  const sddApproved = !!approvals?.["SDD.md"]?.approved;
  const testApproved = !!approvals?.["TestPlan.md"]?.approved;
  const approvedCount = useMemo(
    () => Object.values(approvals || {}).filter((a) => a?.approved).length,
    [approvals],
  );
  const docCount = useMemo(() => {
    if (docs?.artifacts) return docs.artifacts.length;
    return Object.keys(versions?.versions || {}).length;
  }, [docs, versions]);

  const workspaceHeroSubtitle = useMemo(() => {
    const parts: string[] = [];
    if (project?.current_phase) {
      parts.push(`Current phase: ${project.current_phase}`);
    }
    if (reqCount > 0) {
      parts.push(`${reqCount} requirement${reqCount === 1 ? "" : "s"} captured`);
    }
    if (docCount) {
      parts.push(`${docCount} document${docCount === 1 ? "" : "s"} generated`);
    }
    const base =
      "Navigate requirements, design, testing, and approvals with live editing and streaming updates.";
    if (parts.length === 0) return base;
    return `${base} ${parts.join(" · ")}.`;
  }, [project?.current_phase, reqCount, docCount]);

  const workspaceQuickLinks = useMemo(
    () => [
      {
        id: "requirements",
        label: "Requirements",
        description: "Chat, inline Markdown edits, and live preview streaming.",
        action: () => routeToTab("Requirements"),
      },
      {
        id: "docs",
        label: "Docs",
        description: "Browse, approve, and download generated artifacts.",
        action: () => routeToTab("Docs"),
      },
      {
        id: "design",
        label: "Design",
        description: "Answer open questions and capture architecture decisions.",
        action: () => routeToTab("Design"),
      },
      {
        id: "settings",
        label: "Settings",
        description: "Manage stored context, impact analysis, and approvals.",
        action: () => routeToTab("Settings"),
      },
    ],
    [routeToTab],
  );
  const generationProgress = useMemo(() => {
    if (!docGeneration.active && !docGeneration.cancelRequested) return 0;
    switch (docGeneration.stage) {
      case "context":
        return 0.33;
      case "llm":
        return 0.66;
      case "post":
        return docGeneration.cancelRequested ? 0.66 : 0.9;
      default:
        return docGeneration.cancelRequested
          ? 0.66
          : docGeneration.active
            ? 0.2
            : 1;
    }
  }, [
    docGeneration.active,
    docGeneration.cancelRequested,
    docGeneration.stage,
  ]);
  const generationProgressText = useMemo(() => {
    switch (docGeneration.stage) {
      case "context":
        return "Generating context...";
      case "llm":
        return "Generating documents using AI...";
      case "post":
        return docGeneration.cancelRequested
          ? "Cancelling document generation..."
          : "Finalizing document generation...";
      default:
        return docGeneration.active
          ? "Generating documents..."
          : "Document generation complete.";
    }
  }, [
    docGeneration.active,
    docGeneration.cancelRequested,
    docGeneration.stage,
  ]);

  const currentIndex = useMemo(() => {
    let idx = 0; // Charter
    if (charterApproved) idx = 1; // Requirements
    if (reqCount > 0) idx = 2; // Specifications
    if (srsApproved) idx = 3; // Design
    if (sddApproved) idx = 4; // Implementation
    if (testApproved) idx = 6; // Deployment
    return idx;
  }, [charterApproved, reqCount, srsApproved, sddApproved, testApproved]);

  const GenerationStatus = () => {
    const show = docGeneration.active || docGeneration.cancelRequested;
    if (!show) return null;
    const percent = Math.min(Math.max(generationProgress, 0), 1);
    const pct = Math.round(percent * 100);
    return (
      <div
        className="card"
        style={{ marginBottom: 12 }}
        role="status"
        aria-live="polite"
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 8,
              alignItems: "center",
            }}
          >
            <strong>
              {docGeneration.cancelRequested
                ? "Cancelling document generation"
                : "Generating documents"}
            </strong>
            <span className="muted">
              {docGeneration.message || generationProgressText}
            </span>
          </div>
          {docGenerationLog.length > 0 && (
            <ul
              style={{
                margin: "4px 0 0",
                padding: 0,
                listStyle: "none",
                display: "grid",
                gap: 4,
              }}
            >
              {docGenerationLog.map((entry, idx) => (
                <li
                  key={`${entry.timestamp}-${idx}`}
                  className="muted"
                  style={{ fontSize: 13 }}
                >
                  {entry.text}
                </li>
              ))}
            </ul>
          )}
          <div
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            role="progressbar"
            style={{
              position: "relative",
              width: "100%",
              height: 8,
              borderRadius: 999,
              background: "var(--surface-2)",
            }}
          >
            <div
              style={{
                width: `${pct}%`,
                transition: "width 180ms ease-out",
                height: "100%",
                borderRadius: 999,
                background: "var(--accent, var(--primary))",
              }}
            />
          </div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: 8,
            }}
          >
            <span className="muted">Progress: {pct}%</span>
            <button
              className="btn"
              onClick={cancelDocGeneration}
              disabled={docGeneration.cancelRequested}
            >
              {docGeneration.cancelRequested
                ? "Cancel requested…"
                : "Cancel generation"}
            </button>
          </div>
        </div>
      </div>
    );
  };

  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        setNotice(null);
        // If unauthenticated, bounce to login with returnTo
        if (typeof window !== "undefined") {
          // naive check: API call will fail if unauthorized, but check token first for faster UX
          const token =
            typeof window !== "undefined"
              ? window.localStorage.getItem("opnxt_token")
              : null;
          if (!token) {
            const rt = encodeURIComponent(
              window.location.pathname + window.location.search,
            );
            window.location.href = `/login?returnTo=${rt}`;
            return;
          }
        }
        const p = await getProject(id);
        setProject(p);
        // Do not auto-load existing document contents on landing; show empty state until user acts
        // Load version metadata
        try {
          const v = await listDocumentVersions(id);
          setVersions(v);
        } catch {}
        // Fetch stored context
        try {
          const c = await getProjectContext(id);
          setCtx(c);
          const data = (c && c.data) || ({} as any);
          const planning = (data.summaries && data.summaries.Planning) || "";
          const reqs = (data.answers && data.answers.Requirements) || [];
          setCtxPlanning(String(planning || ""));
          setCtxRequirements(Array.isArray(reqs) ? reqs.join("\n") : "");
          const aps =
            data.approvals && typeof data.approvals === "object"
              ? data.approvals
              : {};
          setApprovals(aps);
        } catch {}
      } catch (e: any) {
        setError(e?.message || String(e));
        if (typeof window !== "undefined") {
          const rt = encodeURIComponent(
            window.location.pathname + window.location.search,
          );
          window.location.href = `/login?returnTo=${rt}`;
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  async function loadLatestDocs() {
    if (!id) return;
    try {
      const v = await listDocumentVersions(id);
      setVersions(v);
      const files = Object.keys(v.versions || {});
      if (files.length === 0) {
        setDocs(null);
        setSelected(null);
        return;
      }
      const artifacts: { filename: string; content: string }[] = [];
      for (const fname of files) {
        const list = v.versions[fname] || [];
        const latest = list.length ? list[list.length - 1].version : undefined;
        if (latest === undefined) continue;
        const dv = await getDocumentVersion(id, fname, latest);
        artifacts.push({ filename: dv.filename, content: dv.content });
      }
      const resp = { project_id: id, artifacts } as DocGenResponse;
      setDocs(resp);
      if (artifacts.length > 0) setSelected(artifacts[0].filename);
    } catch (e: any) {
      // Non-fatal: show empty state; generation can be triggered manually
      setDocs(null);
      setSelected(null);
    }
  }

  const combinedArtifacts = useMemo(() => {
    if (streamedDocuments.length > 0) return streamedDocuments;
    if (docs?.artifacts) return docs.artifacts;
    return [] as DocGenResponse["artifacts"];
  }, [streamedDocuments, docs]);

  const selectedArtifact = useMemo(() => {
    if (!selected) return null;
    const streamed = streamedDocumentMap[selected];
    if (streamed) return streamed;
    if (docs?.artifacts) {
      return docs.artifacts.find((a) => a.filename === selected) || null;
    }
    return null;
  }, [selected, streamedDocumentMap, docs]);

  useEffect(() => {
    if (!selectedArtifact && previewModalOpen) {
      setPreviewModalOpen(false);
    }
  }, [selectedArtifact, previewModalOpen]);

  const selectedApproval = selected ? approvals?.[selected] : undefined;

  useEffect(() => {
    if (!editMode) {
      const meta = (selectedArtifact as any)?.meta || {};
      setEditDraft(selectedArtifact?.content ?? "");
      setEditSummary(typeof meta?.summary === "string" ? meta.summary : "");
      setEditSection(typeof meta?.section === "string" ? meta.section : "");
      if (!editChangeDescription) {
        setEditChangeDescription("");
      }
    }
  }, [selectedArtifact, editMode, editChangeDescription]);

  useEffect(() => {
    setLastSavedRevision(null);
    setEditError(null);
    setEditMode(false);
  }, [selected]);

  const canSaveEdit = useMemo(
    () => Boolean(selected && !savingEdit && editDraft.trim().length > 0),
    [selected, savingEdit, editDraft],
  );

  const showLivePreview = useMemo(
    () => Boolean(!editMode && livePreview && streamDraftActive),
    [editMode, livePreview, streamDraftActive],
  );

  const streamNotice = useMemo(() => {
    if (streamError) return { variant: "error" as const, text: streamError };
    if (!streamConnected)
      return {
        variant: "warn" as const,
        text: "Reconnecting you to the live builder…",
      };
    if (heartbeatStale)
      return {
        variant: "warn" as const,
        text: "Haven’t heard back from the stream in a moment—tap reconnect if you stop seeing updates.",
      };
    if (streamDraftActive)
      return {
        variant: "info" as const,
        text: "✨ I’m weaving your latest details into the draft right now."
        ,
      };
    if (streamStatus?.message) {
      const suffix = streamStatus.stage ? ` (stage: ${streamStatus.stage})` : "";
      return {
        variant: "info" as const,
        text: `✅ ${streamStatus.message}${suffix}`,
      };
    }
    return null;
  }, [streamError, streamConnected, heartbeatStale, streamDraftActive, streamStatus]);

  const liveUpdateEntries = useMemo(() => {
    if (!recentUpdates?.length)
      return [] as {
        key: string;
        label: string;
        detail?: string | null;
        messageId?: string | null;
        timestamp?: string | null;
        revision?: number | null;
        diff?: string | null;
      }[];
    return recentUpdates
      .slice()
      .reverse()
      .map((update, index) => {
        const key = `${update.ts || index}-${update.type}-${update.filename ?? ""}`;
        const baseTs = update.ts ? new Date(update.ts).toLocaleTimeString() : null;
        const summaryDetail = update.summary ?? update.message ?? null;
        const changeDetail = update.changeDescription ?? null;
        const diffDetail = update.diff ? update.diff.slice(0, 200) : null;
        switch (update.type) {
          case "document_update": {
            const fileLabel = update.filename ? `Updated ${update.filename}` : "Document updated";
            const sectionDetail = update.section ? `Section ${update.section}` : null;
            const combinedDetail = summaryDetail || changeDetail || sectionDetail || diffDetail;
            return {
              key,
              label: fileLabel,
              detail: combinedDetail ?? (update.stage ? `Stage ${update.stage}` : null),
              messageId: update.messageId ?? null,
              timestamp: baseTs,
              revision: typeof update.revision === "number" ? update.revision : null,
              diff: diffDetail,
            };
          }
          case "draft_update":
            return {
              key,
              label: update.filename ? `Drafting ${update.filename}` : "Draft preview updating",
              detail: update.preview ? update.preview.slice(0, 120) : "Live preview refreshed",
              messageId: update.messageId ?? null,
              timestamp: baseTs,
            };
          case "status":
            return {
              key,
              label: update.message ? update.message : "Status update",
              detail: update.stage ? `Stage ${update.stage}` : null,
              messageId: update.messageId ?? null,
              timestamp: baseTs,
              revision: typeof update.revision === "number" ? update.revision : null,
            };
          case "error":
            return {
              key,
              label: update.message ? update.message : "Stream error",
              detail: "Check console or retry generation.",
              messageId: update.messageId ?? null,
              timestamp: baseTs,
              revision: typeof update.revision === "number" ? update.revision : null,
            };
          default:
            return {
              key,
              label: "Update received",
              detail: null,
              messageId: update.messageId ?? null,
              timestamp: baseTs,
              revision: typeof update.revision === "number" ? update.revision : null,
            };
        }
      })
      .slice(0, 6);
  }, [recentUpdates]);

  const openChatForMessage = useCallback(
    (messageId?: string | null) => {
      if (!messageId) return;
      setChipPrefill(
        `Let’s refine the part linked to chat message ${messageId}. Here’s what I’d like to adjust: `,
      );
      routeToTab("Requirements");
    },
    [routeToTab],
  );

  const selectedMeta = useMemo(() => {
    const candidate = (selectedArtifact as any)?.meta;
    if (!candidate || typeof candidate !== "object") return null;
    return candidate as Record<string, any>;
  }, [selectedArtifact]);

  const selectedMetaDetails = useMemo(() => {
    if (!selectedMeta) return [] as { label: string; value: string }[];
    const details: { label: string; value: string }[] = [];
    const revisionValue =
      selectedArtifact?.revision != null
        ? `r${selectedArtifact.revision}`
        : selectedMeta.revision != null
          ? `r${selectedMeta.revision}`
          : null;
    if (revisionValue) {
      details.push({ label: "Revision", value: revisionValue });
    }
    if (selectedMeta.summary) {
      details.push({ label: "Summary", value: String(selectedMeta.summary) });
    }
    if (selectedMeta.section) {
      details.push({ label: "Section", value: String(selectedMeta.section) });
    }
    if (selectedMeta.change_description) {
      details.push({ label: "Change", value: String(selectedMeta.change_description) });
    }
    if (selectedMeta.message_id) {
      details.push({ label: "Message", value: String(selectedMeta.message_id) });
    }
    if (selectedMeta.manual_edit) {
      const editor = selectedMeta.edited_by ? String(selectedMeta.edited_by) : "Manual edit";
      const when = selectedMeta.edited_at
        ? new Date(selectedMeta.edited_at).toLocaleString()
        : undefined;
      details.push({
        label: "Edited",
        value: when ? `${editor} • ${when}` : editor,
      });
    }
    return details;
  }, [selectedMeta, selectedArtifact?.revision]);

  const beginEdit = useCallback(() => {
    if (!selectedArtifact) return;
    setEditError(null);
    setEditMode(true);
    setEditDraft(selectedArtifact.content ?? "");
  }, [selectedArtifact]);

  const cancelEdit = useCallback(() => {
    setEditMode(false);
    setEditError(null);
    const meta = (selectedArtifact as any)?.meta || {};
    setEditDraft(selectedArtifact?.content ?? "");
    setEditSummary(typeof meta?.summary === "string" ? meta.summary : "");
    setEditSection(typeof meta?.section === "string" ? meta.section : "");
    setEditChangeDescription("");
  }, [selectedArtifact]);

  const saveEdit = useCallback(async () => {
    if (!id || !selected) return;
    const payload: DocumentEditRequest = {
      content: editDraft,
      summary: editSummary.trim() ? editSummary.trim() : undefined,
      section: editSection.trim() ? editSection.trim() : undefined,
      change_description: editChangeDescription.trim() ? editChangeDescription.trim() : undefined,
    };
    try {
      setSavingEdit(true);
      setEditError(null);
      const response = await patchProjectDocument(id, selected, payload);
      setNotice(`Saved ${response.filename} (revision ${response.revision}).`);
      setLastSavedRevision(response.revision);
      setEditMode(false);
      const meta = response.meta || {};
      setEditSummary(typeof meta?.summary === "string" ? meta.summary : "");
      setEditSection(typeof meta?.section === "string" ? meta.section : "");
      setEditChangeDescription("");
      setDocs((prev) => {
        if (!prev) return prev;
        const artifacts = prev.artifacts || [];
        const found = artifacts.some((a) => a.filename === response.filename);
        const updated = found
          ? artifacts.map((a) =>
              a.filename === response.filename
                ? { ...a, content: response.content, meta: response.meta, revision: response.revision }
                : a,
            )
          : [
              ...artifacts,
              {
                filename: response.filename,
                content: response.content,
                meta: response.meta,
                revision: response.revision,
              },
            ];
        return { ...prev, artifacts: updated } as DocGenResponse;
      });
    } catch (err: any) {
      const msg = err?.message || "Unable to save edit.";
      setEditError(msg);
    } finally {
      setSavingEdit(false);
    }
  }, [id, selected, editDraft, editSummary, editSection, editChangeDescription]);

  useEffect(() => {
    if (!id || !selected || lastSavedRevision === null) return;
    trackEvent("project_document_edit_saved", {
      projectId: id,
      filename: selected,
      revision: lastSavedRevision,
      summary: editSummary || undefined,
      section: editSection || undefined,
    });
  }, [id, selected, lastSavedRevision, editSummary, editSection]);

  useEffect(() => {
    if (!id) return;
    if (streamError && streamError !== lastStreamErrorRef.current) {
      trackEvent("project_document_stream_error", {
        projectId: id,
        message: streamError,
      });
      lastStreamErrorRef.current = streamError;
    }
    if (!streamError) {
      lastStreamErrorRef.current = null;
    }
  }, [id, streamError]);

  useEffect(() => {
    if (!id) return;
    if (prevStreamConnectedRef.current === null) {
      prevStreamConnectedRef.current = streamConnected;
      return;
    }
    if (prevStreamConnectedRef.current !== streamConnected) {
      trackEvent("project_document_stream_status", {
        projectId: id,
        connected: streamConnected,
      });
    }
    prevStreamConnectedRef.current = streamConnected;
  }, [id, streamConnected]);

  const artifactSummaries = useMemo(() => {
    const decorate = (filename: string) => {
      const approval = approvals?.[filename];
      const versionInfo = versions?.versions?.[filename]?.slice(-1)[0];
      const status = approval?.approved && approval?.approved_at
        ? `Approved · ${new Date(approval.approved_at).toLocaleDateString()}`
        : versionInfo
          ? `Updated · ${new Date(versionInfo.created_at).toLocaleDateString()}`
          : undefined;
      return {
        filename,
        label: filename,
        status,
      };
    };
    const seen = new Set<string>();
    const filenames: string[] = [];
    combinedArtifacts.forEach((artifact) => {
      if (!artifact?.filename || seen.has(artifact.filename)) return;
      seen.add(artifact.filename);
      filenames.push(artifact.filename);
    });
    if (filenames.length === 0) {
      const versionMap = versions?.versions || {};
      Object.keys(versionMap).forEach((fname) => {
        if (!seen.has(fname)) filenames.push(fname);
      });
    }
    return filenames.map((fname) => decorate(fname));
  }, [approvals, combinedArtifacts, versions]);

  const hasDocs = useMemo(
    () => artifactSummaries.length > 0,
    [artifactSummaries],
  );

  const sddArtifact = useMemo(() => {
    if (!docs) return null;
    return docs.artifacts.find((a) => /sdd/i.test(a.filename)) || null;
  }, [docs]);

  const testPlanArtifact = useMemo(() => {
    if (!docs) return null;
    return docs.artifacts.find((a) => /test\s*plan/i.test(a.filename)) || null;
  }, [docs]);

  // Parse Open Questions from SDD content
  useEffect(() => {
    const content = sddArtifact?.content || "";
    if (!content) {
      setDesignQuestions([]);
      return;
    }
    function extractOpenQuestionsFromMarkdown(md: string): string[] {
      const lines = md.split(/\r?\n/);
      let idx = -1;
      for (let i = 0; i < lines.length; i++) {
        if (/\bOpen\s*Questions\b/i.test(lines[i])) {
          idx = i;
          break;
        }
      }
      if (idx < 0) return [];
      const qs: string[] = [];
      // Capture inline question(s) on the same line, e.g., "... Open Questions: What ...?"
      const sameLine = lines[idx];
      const inline = sameLine
        .replace(/^.*\bOpen\s*Questions\b\s*[:\-–—]?\s*/i, "")
        .trim();
      if (inline) {
        // Split by typical delimiters if multiple questions present
        const parts = inline
          .split(/(?<=\?)\s+|;\s+/)
          .map((s) => s.trim())
          .filter(Boolean);
        for (const p of parts) {
          const q = p.endsWith("?") ? p : p ? p + "?" : "";
          if (q) qs.push(q);
        }
      }
      // Capture following bullet/lines until next heading
      for (let i = idx + 1; i < lines.length; i++) {
        const ln = lines[i];
        if (/^\s*#{1,6}\s+/.test(ln)) break; // next markdown heading
        const m = ln.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/);
        const txt = (m ? m[1] : ln).trim();
        if (!txt) continue;
        // Accept explicit Q: prefix or question mark
        let q = txt.replace(/^Q[:\s-]+/i, "").trim();
        if (!q) continue;
        if (!/[?]$/.test(q)) q += "?";
        qs.push(q);
      }
      // Deduplicate, keep order
      const seen = new Set<string>();
      const uniq: string[] = [];
      for (const q of qs) {
        if (!seen.has(q)) {
          seen.add(q);
          uniq.push(q);
        }
      }
      return uniq;
    }
    setDesignQuestions(extractOpenQuestionsFromMarkdown(content));
  }, [sddArtifact?.content]);

  function onAnswerChange(idx: number, value: string) {
    setDesignAnswers((prev) => ({ ...prev, [idx]: value }));
  }

  async function applyDesignAnswersToContext() {
    if (!id) return;
    const answered = designQuestions
      .map((q, i) => ({ q, a: (designAnswers[i] || "").trim() }))
      .filter((x) => x.a.length > 0);
    if (answered.length === 0) {
      setQaNotice("Add at least one answer to apply.");
      return;
    }
    try {
      setQaNotice(null);
      const current = await getProjectContext(id);
      const data: any = current && current.data ? { ...current.data } : {};
      const answers: Record<string, any> = Array.isArray(data.answers)
        ? {}
        : data.answers || {};
      const existing: string[] = Array.isArray(answers["Design Answers"])
        ? answers["Design Answers"]
        : [];
      const merged = existing.slice();
      for (const item of answered) {
        const entry = `Q: ${item.q}\nA: ${item.a}`;
        if (!merged.includes(entry)) merged.push(entry);
      }
      const payload = {
        data: { ...data, answers: { ...answers, "Design Answers": merged } },
      } as any;
      await putProjectContext(id, payload);
      setQaNotice(`Applied ${answered.length} answer(s) to Stored Context.`);
    } catch (e: any) {
      setQaNotice(e?.message || String(e));
    }
  }

  async function applyAndGenerateFromDesign() {
    try {
      setDesignGenerating(true);
      await applyDesignAnswersToContext();
      await onAIGenerateSmart();
    } finally {
      setDesignGenerating(false);
    }
  }

  function discussInChat(question: string) {
    try {
      setChipPrefill(
        `Open Question from SDD: ${question}\nMy answer/thoughts: `,
      );
    } catch {}
    try {
      router.push(`/projects/${id}?tab=Requirements`);
    } catch {}
  }

  function cancelDocGeneration() {
    setDocGeneration((prev) => {
      if (!prev.active) return prev;
      if (prev.cancelRequested) return prev;
      setNotice(
        "Cancel request noted. The current generation will finish shortly.",
      );
      appendDocLog("Cancel requested. Waiting for current step to finish…");
      return { ...prev, cancelRequested: true };
    });
  }

  async function onRegenerate() {
    if (!id) return;
    try {
      resetDocGenerationLog("Refreshing stored context…");
      setDocGeneration({
        active: true,
        stage: "context",
        message: "Refreshing stored context…",
        cancelRequested: false,
      });
      setNotice("Refreshing stored context…");
      setLoading(true);
      setError(null);
      setDocGeneration((prev) =>
        prev.active
          ? { ...prev, stage: "llm", message: "Requesting document refresh…" }
          : prev,
      );
      appendDocLog("Requesting document refresh…");
      const resp = await generateDocuments(id, {
        traceability_overlay: overlayOn,
      });
      setDocGeneration((prev) =>
        prev.active
          ? { ...prev, stage: "post", message: "Updating previews…" }
          : prev,
      );
      appendDocLog("Updating previews…");
      setDocs(resp);
      if (resp.artifacts.length > 0) {
        const keep =
          selected && resp.artifacts.find((a) => a.filename === selected);
        setSelected(keep ? keep.filename : resp.artifacts[0].filename);
      }
      setNotice(`Generated ${resp.artifacts.length} documents.`);
      appendDocLog(`Generated ${resp.artifacts.length} documents.`);
    } catch (e: any) {
      setError(e?.message || String(e));
      appendDocLog(`Error: ${e?.message || String(e)}`);
    } finally {
      setLoading(false);
      setDocGeneration({ active: false, stage: "idle" });
      appendDocLog("Document refresh finished.");
    }
  }

  // Convenience: generate backlog with AI option enabled
  async function onGenerateBacklogSmart() {
    try {
      setIncludeBacklog(true);
      await onAIGenerateSmart();
    } finally {
      // keep includeBacklog on for subsequent runs
    }
  }

  // Regenerate only the SDD using AI and keep other artifacts intact
  async function onAIGenerateSDD() {
    if (!id) return;
    try {
      setLoading(true);
      setError(null);
      const latest = await getProjectContext(id);
      setCtx(latest);
      const prompt = buildSmartPrompt(latest);
      const req: any = {
        input_text: prompt,
        include_backlog: includeBacklog,
        doc_types: ["SDD"],
      };
      const resp = await aiGenerateDocuments(id, req);
      setDocs((prev) => {
        const others = (prev?.artifacts || []).filter(
          (a) => !/sdd/i.test(a.filename),
        );
        return {
          project_id: id,
          artifacts: [...others, ...resp.artifacts],
        } as DocGenResponse;
      });
      const sdd = resp.artifacts.find((a) => /sdd/i.test(a.filename));
      if (sdd) setSelected(sdd.filename);
      setNotice("AI-generated SDD.");
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  const updateApproval = useCallback(
    async (filename: string, approved: boolean) => {
      if (!id) return;
      try {
        setApprovalBusy(true);
        const current = await getProjectContext(id);
        const data: any = current && current.data ? { ...current.data } : {};
        const aps: Record<string, { approved: boolean; approved_at?: string }> =
          data.approvals && typeof data.approvals === "object"
            ? { ...data.approvals }
            : {};
        aps[filename] = { approved, approved_at: new Date().toISOString() };
        const payload = { data: { ...data, approvals: aps } } as any;
        await putProjectContext(id, payload);
        setApprovals(aps);
        setNotice(approved ? `Approved ${filename}` : `Unapproved ${filename}`);
      } catch (e: any) {
        setError(e?.message || String(e));
      } finally {
        setApprovalBusy(false);
      }
    },
    [id],
  );

  const ensureArtifactContent = useCallback(
    async (fname: string) => {
      if (!id || !fname) return;
      const hasContent = docs?.artifacts?.some(
        (a) => a.filename === fname && typeof a.content === "string",
      );
      if (hasContent) return;
      const list = versions?.versions?.[fname];
      if (!list || list.length === 0) return;
      const latest = list[list.length - 1];
      try {
        const dv = await getDocumentVersion(id, fname, latest.version);
        setDocs((prev) => {
          const base = prev || ({
            project_id: id,
            artifacts: [],
          } as DocGenResponse);
          const others = (base.artifacts || []).filter(
            (a) => a.filename !== fname,
          );
          return {
            ...base,
            artifacts: [
              ...others,
              { filename: dv.filename, content: dv.content } as DocGenResponse["artifacts"][number],
            ],
          } as DocGenResponse;
        });
        setPreviewVersion({ filename: dv.filename, version: dv.version });
      } catch (e: any) {
        setError(e?.message || String(e));
      }
    },
    [docs, id, versions],
  );

  const handleSelectArtifact = useCallback(
    (fname: string) => {
      setSelected(fname);
    },
    [],
  );

  useEffect(() => {
    if (selected || artifactSummaries.length === 0) return;
    setSelected(artifactSummaries[0].filename);
  }, [artifactSummaries, selected]);

  useEffect(() => {
    if (!selected) return;
    void ensureArtifactContent(selected);
  }, [selected, ensureArtifactContent]);

  const handleApproveSelected = useCallback(async () => {
    if (!selected) return;
    await updateApproval(selected, true);
  }, [selected, updateApproval]);

  const handleRejectSelected = useCallback(async () => {
    if (!selected) return;
    await updateApproval(selected, false);
  }, [selected, updateApproval]);

  async function onPreviewVersion(fname: string, version: number) {
    if (!id) return;
    try {
      setError(null);
      const v = await getDocumentVersion(id, fname, version);
      // Create a transient artifact for preview
      const artifact = { filename: v.filename, content: v.content };
      // Replace or add to docs preview state without altering saved files
      setDocs((prev) => {
        const base = prev || ({ project_id: id, artifacts: [] } as DocGenResponse);
        const others = (base.artifacts || []).filter(
          (a) => a.filename !== v.filename,
        );
        return {
          ...base,
          artifacts: [...others, artifact],
        } as DocGenResponse;
      });
      setSelected(v.filename);
      setPreviewVersion({ filename: v.filename, version: v.version });
      setNotice(`Previewing ${v.filename} v${v.version}`);
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  }

  function buildSmartPrompt(overrideCtx?: ProjectContext | null): string {
    const sourceCtx = overrideCtx ?? ctx;
    const data: any = sourceCtx?.data || {};
    const planning = data?.summaries?.Planning || "";
    const reqs: string[] = Array.isArray(data?.answers?.Requirements)
      ? data.answers.Requirements
      : [];
    const parts = [
      planning ? `Planning Summary:\n${planning}` : "",
      reqs.length ? `Requirements:\n- ${reqs.join("\n- ")}` : "",
    ].filter(Boolean);
    // Include Design Q&A if present
    const answered = designQuestions
      .map((q, i) => ({ q, a: (designAnswers[i] || "").trim() }))
      .filter((x) => x.a.length > 0);
    if (answered.length) {
      const qa = answered.map((x) => `Q: ${x.q}\nA: ${x.a}`).join("\n\n");
      parts.push(`Design Q&A:\n${qa}`);
    }
    if (parts.length) return parts.join("\n\n");

    // 4) Last resort default
    return "Generate the standard documents (Project Charter, SRS, SDD, Test Plan) for this project based on current context.";
  }

  async function onAIGenerateSmart() {
    if (!id) return;
    try {
      resetDocGenerationLog("Gathering project context…");
      setDocGeneration({
        active: true,
        stage: "context",
        message: "Gathering project context…",
        cancelRequested: false,
      });
      setNotice("Gathering project context…");
      setLoading(true);
      setError(null);
      // Refresh context to include any recent ChatPanel applies
      const latest = await getProjectContext(id);
      setCtx(latest);
      setDocGeneration((prev) =>
        prev.active
          ? { ...prev, stage: "llm", message: "Calling language model…" }
          : prev,
      );
      appendDocLog("Calling language model…");
      const prompt = buildSmartPrompt(latest);
      const req: any = { input_text: prompt, include_backlog: includeBacklog };
      const resp = await aiGenerateDocuments(id, req);
      setDocGeneration((prev) =>
        prev.active
          ? { ...prev, stage: "post", message: "Formatting artifacts…" }
          : prev,
      );
      appendDocLog("Formatting artifacts…");
      setDocs(resp);
      if (resp.artifacts.length > 0) setSelected(resp.artifacts[0].filename);
      setNotice(`AI-generated ${resp.artifacts.length} documents.`);
      appendDocLog(`Generated ${resp.artifacts.length} documents.`);
    } catch (e: any) {
      setError(e?.message || String(e));
      appendDocLog(`Error: ${e?.message || String(e)}`);
    } finally {
      setLoading(false);
      setDocGeneration({ active: false, stage: "idle" });
      appendDocLog("Generation run finished.");
    }
  }

  async function onSaveContext() {
    if (!id) return;
    try {
      setSavingCtx(true);
      const answers: Record<string, string[]> = {};
      const summaries: Record<string, string> = {};
      const reqs = ctxRequirements
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean)
        .map((s) => {
          const lower = s.toLowerCase();
          if (
            lower.startsWith("the system shall") ||
            lower.startsWith("shall ") ||
            lower.startsWith("system shall")
          )
            return s;
          return `The system SHALL ${s}.`;
        });
      if (reqs.length) answers["Requirements"] = reqs;
      if (ctxPlanning.trim()) summaries["Planning"] = ctxPlanning.trim();
      const payload: ProjectContext = { data: {} as any };
      if (Object.keys(answers).length) (payload.data as any).answers = answers;
      if (Object.keys(summaries).length)
        (payload.data as any).summaries = summaries;
      const saved = await putProjectContext(id, payload);
      setCtx(saved);
      setNotice("Context saved.");
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setSavingCtx(false);
    }
  }

  async function onGenerateWithStoredContext() {
    if (!id) return;
    try {
      setLoading(true);
      setError(null);
      const resp = await generateDocuments(id, {
        traceability_overlay: overlayOn,
      });
      setDocs(resp);
      if (resp.artifacts.length > 0) setSelected(resp.artifacts[0].filename);
      setNotice("Generated using stored context.");
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function onAnalyzeImpacts() {
    if (!id) return;
    try {
      setAnalyzing(true);
      setError(null);
      const changed = frInput
        .split(/[\,\n]/)
        .map((s) => s.trim())
        .filter(Boolean);
      const resp = await computeImpacts(id, changed);
      setImpacts(resp);
      setNotice("Impact analysis complete.");
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setAnalyzing(false);
    }
  }

  // Build tab contents
  const OverviewTab = (
    <div>
      {project && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div>
            <strong>ID:</strong> {project.project_id}
          </div>
          <div>
            <strong>Name:</strong> {project.name}
          </div>
          <div>
            <strong>Phase:</strong> {project.current_phase}
          </div>
        </div>
      )}
      {/* KPIs */}
      <div
        className="grid-3"
        aria-label="Project KPIs"
        style={{ marginBottom: 12 }}
      >
        <Stat label="Requirements captured" value={String(reqCount)} />
        <Stat label="Documents generated" value={String(docCount || 0)} />
        <Stat label="Approved docs" value={String(approvedCount)} />
      </div>

      <div className="grid-2">
        {/* Phase Gate Summary */}
        <div className="card" aria-label="Phase Gate">
          <strong>Phase Gate</strong>
          <div style={{ marginTop: 8 }}>
            <Stepper
              steps={[
                { id: "charter", label: "Charter" },
                { id: "requirements", label: "Requirements" },
                { id: "specs", label: "Specifications" },
                { id: "design", label: "Design" },
                { id: "impl", label: "Implementation" },
                { id: "test", label: "Testing" },
                { id: "deploy", label: "Deployment" },
              ]}
              currentIndex={currentIndex}
            />
            <ul style={{ marginTop: 8 }}>
              <li>Charter approved: {charterApproved ? "Yes" : "No"}</li>
              <li>
                Requirements captured:{" "}
                {reqCount > 0 ? `${reqCount} item(s)` : "No"}
              </li>
              <li>SRS approved: {srsApproved ? "Yes" : "No"}</li>
              <li>SDD approved: {sddApproved ? "Yes" : "No"}</li>
              <li>Test Plan approved: {testApproved ? "Yes" : "No"}</li>
            </ul>
          </div>
        </div>

        {/* Quick Links */}
        <div className="card" aria-label="Quick Links">
          <strong>Quick Links</strong>
          <div
            style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}
          >
            <Link
              className="btn btn-primary"
              href={`/projects/${id}?tab=Requirements`}
            >
              Open Requirements Chat
            </Link>
            <Link className="btn" href={`/projects/${id}?tab=Backlog`}>
              Open Backlog
            </Link>
            <Link className="btn" href={`/projects/${id}?tab=Tests`}>
              Open Tests
            </Link>
          </div>
        </div>
      </div>

      {/* Recent Artifacts */}
      <div className="card" style={{ marginTop: 12 }}>
        <strong>Recent Artifacts</strong>
        {artifactSummaries.length === 0 ? (
          <div className="muted">No documents generated yet.</div>
        ) : (
          <DocList
            artifacts={artifactSummaries}
            selected={selected}
            approvals={approvals}
            onSelect={handleSelectArtifact}
          />
        )}
      </div>
    </div>
  );

  const RequirementsTab = (
    <div>
      {/* KPIs */}
      <div
        className="grid-3"
        aria-label="Project KPIs"
        style={{ marginBottom: 12 }}
      >
        <Stat label="Requirements captured" value={String(reqCount)} />
        <Stat label="Documents generated" value={String(docCount || 0)} />
        <Stat label="Approved docs" value={String(approvedCount)} />
      </div>
      <GenerationStatus />
      <NextAction
        message={
          hasDocs
            ? "Review generated artifacts on the right or switch to the Docs tab to manage versions and downloads."
            : "Generate documents with AI now, then refine with chat and regenerate."
        }
        primary={{
          label: "Generate with AI",
          onClick: onAIGenerateSmart,
          variant: "primary",
        }}
        secondary={[
          { label: "Regenerate", onClick: onRegenerate },
        ]}
      />
      <div className="columns-23" style={{ marginTop: 12 }}>
        {/* Left: Chat + Builder */}
        <div className="vstack" style={{ minWidth: 0 }}>
          <div className="card" style={{ marginBottom: 16 }}>
            <ChatPanel
              projectId={id}
              prefill={chipPrefill}
              onPrefillConsumed={() => setChipPrefill(undefined)}
              onRegenerateRequested={onRegenerate}
              onAIGenerateRequested={onAIGenerateSmart}
              autoGenerateDefault={false}
              onOrchestrateRequested={() => triggerOrchestration()}
              orchestration={{
                running: orchestrating,
                error: orchestrateError,
                timeline: orchestrateTimeline,
                runId: orchestrateResult?.run_id ?? null,
              }}
            />
          </div>
        </div>
        {/* Right: Docs preview + versions to be visible alongside chat */}
        <div className="vstack" style={{ minWidth: 0 }}>
          <div className="card artifact-inspector" aria-live="polite">
            <div className="artifact-inspector__header">
              <div className="artifact-inspector__title">
                <strong>Artifacts</strong>
                <button className="btn" onClick={onRegenerate} disabled={loading}>
                  {loading ? "Regenerating…" : "Regenerate"}
                </button>
              </div>
              {project && (
                <a className="btn" href={zipUrl(project.project_id)}>
                  Download (.zip)
                </a>
              )}
            </div>
            <div className="artifact-inspector__body">
              <div className="artifact-inspector__list">
                {artifactSummaries.length === 0 ? (
                  <div className="muted">No documents generated yet.</div>
                ) : (
                  <DocList
                    artifacts={artifactSummaries}
                    selected={selected}
                    approvals={approvals}
                    onSelect={handleSelectArtifact}
                  />
                )}
              </div>
              <div className="artifact-inspector__preview">
                <div
                  className="doc-preview"
                  aria-busy={(loading || savingEdit || streamDraftActive) || undefined}
                  aria-describedby={streamNotice ? "project-stream-notice" : undefined}
                >
                  {loading && (
                    <div
                      role="status"
                      aria-live="polite"
                      style={{
                        position: "absolute",
                        top: 6,
                        right: 6,
                        background: "var(--surface-1)",
                        border: "1px solid var(--border)",
                        borderRadius: 999,
                        padding: "2px 8px",
                        fontSize: 12,
                        boxShadow: "var(--shadow-sm)",
                      }}
                    >
                      <span aria-hidden>⏳</span> Generating…
                    </div>
                  )}
                  {savingEdit && (
                    <div
                      role="status"
                      aria-live="polite"
                      style={{
                        position: "absolute",
                        top: 6,
                        left: 6,
                        background: "var(--surface-1)",
                        border: "1px solid var(--border)",
                        borderRadius: 999,
                        padding: "2px 8px",
                        fontSize: 12,
                        boxShadow: "var(--shadow-sm)",
                      }}
                    >
                      <span aria-hidden>💾</span> Saving edit…
                    </div>
                  )}
                  {streamNotice && (
                    <div
                      id="project-stream-notice"
                      className={`stream-notice stream-notice--${streamNotice.variant}`}
                      role={streamNotice.variant === "error" ? "alert" : "status"}
                      aria-live={streamNotice.variant === "error" ? "assertive" : "polite"}
                      style={{
                        position: "absolute",
                        top: 6,
                        right: streamNotice.variant === "error" ? 120 : 6,
                        maxWidth: "60%",
                      }}
                    >
                      {streamNotice.text}
                      {streamNotice.variant !== "error" && (!streamConnected || heartbeatStale) && (
                        <button
                          type="button"
                          className="btn-inline"
                          onClick={reconnectStream}
                          aria-label="Reconnect to the live builder stream"
                        >
                          Reconnect
                        </button>
                      )}
                    </div>
                  )}
                  {selected ? (
                    selectedArtifact ? (
                      editMode ? (
                        <div className="doc-editor">
                          <label className="doc-editor__label" htmlFor="doc-edit-content">
                            Markdown content
                          </label>
                          <textarea
                            id="doc-edit-content"
                            className="doc-editor__textarea"
                            value={editDraft}
                            onChange={(event) => setEditDraft(event.target.value)}
                            rows={24}
                          />
                          <div className="doc-editor__meta-grid">
                            <label>
                              Summary
                              <input
                                type="text"
                                value={editSummary}
                                onChange={(event) => setEditSummary(event.target.value)}
                                placeholder="Optional change summary"
                              />
                            </label>
                            <label>
                              Section
                              <input
                                type="text"
                                value={editSection}
                                onChange={(event) => setEditSection(event.target.value)}
                                placeholder="Optional section"
                              />
                            </label>
                            <label>
                              Change description
                              <input
                                type="text"
                                value={editChangeDescription}
                                onChange={(event) => setEditChangeDescription(event.target.value)}
                                placeholder="Describe the change"
                              />
                            </label>
                          </div>
                          {editError && (
                            <p className="doc-editor__error" role="alert">
                              {editError}
                            </p>
                          )}
                          {lastSavedRevision && (
                            <p className="doc-editor__success" role="status">
                              Saved revision {lastSavedRevision} just now.
                            </p>
                          )}
                          <div className="doc-editor__actions">
                            <button className="btn" type="button" onClick={cancelEdit} disabled={savingEdit}>
                              Cancel
                            </button>
                            <button
                              className="btn btn-primary"
                              type="button"
                              onClick={saveEdit}
                              disabled={!canSaveEdit}
                            >
                              {savingEdit ? "Saving…" : "Save changes"}
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="doc-preview__content">
                          {showLivePreview && (
                            <div className="doc-preview__live">
                              <strong>Live draft</strong>
                              <pre>{livePreview}</pre>
                            </div>
                          )}
                          {liveUpdateEntries.length > 0 && (
                            <div
                              className="doc-preview__updates"
                              role="region"
                              aria-live="polite"
                              aria-atomic="false"
                              aria-relevant="additions text"
                              aria-labelledby="doc-preview-updates-heading"
                            >
                              <strong id="doc-preview-updates-heading">Live updates linked to chat</strong>
                              <ul className="doc-preview__updates-list" role="list">
                                {liveUpdateEntries.map((entry) => (
                                  <li key={entry.key} role="listitem">
                                    <div>
                                      <span>
                                        {entry.timestamp ? `${entry.timestamp} · ` : ""}
                                        {entry.label}
                                      </span>
                                      {typeof entry.revision === "number" && (
                                        <div className="muted" style={{ fontSize: 12 }}>
                                          Revision r{entry.revision}
                                        </div>
                                      )}
                                      {entry.detail && (
                                        <div className="muted" style={{ fontSize: 12 }}>
                                          {entry.detail}
                                        </div>
                                      )}
                                      {entry.diff && (
                                        <details className="doc-preview__diff" style={{ marginTop: 4 }}>
                                          <summary style={{ cursor: "pointer", fontSize: 12 }}>View diff snippet</summary>
                                          <pre style={{ marginTop: 4, fontSize: 12, whiteSpace: "pre-wrap" }}>{entry.diff}</pre>
                                        </details>
                                      )}
                                      <span className="sr-only">
                                        {entry.revision ? `Revision ${entry.revision}. ` : ""}
                                        {entry.detail ? `${entry.detail}. ` : ""}
                                        {entry.diff ? "Diff snippet available." : ""}
                                      </span>
                                    </div>
                                    {entry.messageId && (
                                      <button
                                        type="button"
                                        className="btn-inline"
                                        onClick={() => openChatForMessage(entry.messageId)}
                                        aria-label="Discuss this update in chat"
                                      >
                                        Discuss in chat
                                      </button>
                                    )}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {selectedArtifact.content}
                          </ReactMarkdown>
                          {selectedMetaDetails.length > 0 && (
                            <div className="doc-preview__meta" aria-live="polite">
                              {selectedMetaDetails.map((item) => (
                                <div key={item.label} className="doc-preview__meta-item">
                                  <span className="doc-preview__meta-label">{item.label}</span>
                                  <span className="doc-preview__meta-value">{item.value}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )
                    ) : (
                      <p className="doc-preview__placeholder">Loading latest version…</p>
                    )
                  ) : (
                    <p className="doc-preview__placeholder">
                      Select an artifact to preview it here.
                    </p>
                  )}
                </div>
                <div className="artifact-inspector__quick-actions">
                  <button
                    className="btn"
                    type="button"
                    onClick={() => setPreviewModalOpen(true)}
                    disabled={!selectedArtifact}
                  >
                    Expand
                  </button>
                  <button
                    className="btn"
                    type="button"
                    onClick={() => (editMode ? cancelEdit() : beginEdit())}
                    disabled={!selectedArtifact || savingEdit}
                  >
                    {editMode ? "View mode" : "Edit inline"}
                  </button>
                </div>
                {selected && (
                  <div className="doc-preview__footer">
                    <span
                      className={
                        selectedApproval?.approved
                          ? "doc-preview__status doc-preview__status--approved"
                          : "doc-preview__status doc-preview__status--pending"
                      }
                    >
                      {selectedApproval?.approved
                        ? `Approved • ${new Date(
                            selectedApproval.approved_at || "",
                          ).toLocaleString()}`
                        : "Awaiting approval"}
                    </span>
                    <div className="doc-preview__actions">
                      <button
                        className="btn btn-primary"
                        type="button"
                        onClick={handleApproveSelected}
                        disabled={
                          approvalBusy ||
                          !selected ||
                          selectedApproval?.approved === true
                        }
                      >
                        {approvalBusy ? "Updating…" : "Approve"}
                      </button>
                      <button
                        className="btn"
                        type="button"
                        onClick={handleRejectSelected}
                        disabled={
                          approvalBusy || !selected || selectedApproval?.approved === false
                        }
                      >
                        {approvalBusy ? "Updating…" : "Reject"}
                      </button>
                    </div>
                  </div>
                )}
                <div className="artifact-inspector__versions">
                  <div className="artifact-inspector__versions-header">
                    <strong>Version History</strong>
                    <button
                      className="btn"
                      onClick={async () => {
                        if (!id) return;
                        try {
                          const v = await listDocumentVersions(id);
                          setVersions(v);
                        } catch (e: any) {
                          setError(e?.message || String(e));
                        }
                      }}
                    >
                      Refresh
                    </button>
                  </div>
                  {(!versions || !selected || !versions.versions[selected]) && (
                    <div className="muted">
                      No versions yet for the selected document.
                    </div>
                  )}
                  {versions && selected && versions.versions[selected] && (
                    <ul className="artifact-inspector__versions-list">
                      {versions.versions[selected]
                        .slice()
                        .reverse()
                        .map((v) => (
                          <li key={v.version}>
                            <span>
                              v{v.version} — {new Date(v.created_at).toLocaleString()}
                            </span>
                            {previewVersion?.filename === selected &&
                            previewVersion?.version === v.version ? (
                              <span className="artifact-inspector__version-active">
                                Previewing
                              </span>
                            ) : (
                              <button
                                className="btn"
                                onClick={() => onPreviewVersion(selected, v.version)}
                              >
                                Preview v{v.version}
                              </button>
                            )}
                          </li>
                        ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const DocsTab = (
    <div style={{ display: "grid", gap: 12 }}>
      {/* KPIs + Next Actions */}
      <div className="grid-3" aria-label="Project KPIs">
        <Stat label="Requirements captured" value={String(reqCount)} />
        <Stat label="Documents generated" value={String(docCount || 0)} />
        <Stat label="Approved docs" value={String(approvedCount)} />
      </div>
      <GenerationStatus />
      <NextAction
        message={
          hasDocs
            ? "Preview, approve, or re-generate documents."
            : "No documents yet. Generate from Requirements with AI."
        }
        primary={
          hasDocs
            ? { label: "Regenerate", onClick: onRegenerate }
            : {
                label: "Generate with AI",
                onClick: onAIGenerateSmart,
                variant: "primary",
              }
        }
        secondary={[
          {
            label: "Open Requirements Chat",
            href: `/projects/${id}?tab=Requirements`,
          },
          {
            label: "Download (.zip)",
            href: project ? zipUrl(project.project_id) : undefined,
          },
        ]}
      />
      <div className="card">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <div
            style={{
              display: "inline-flex",
              gap: 12,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            <strong>Artifacts</strong>
            <button className="btn" onClick={onRegenerate} disabled={loading}>
              {loading ? "Regenerating…" : "Regenerate"}
            </button>
          </div>
          {project && (
            <a className="btn" href={zipUrl(project.project_id)}>
              Download (.zip)
            </a>
          )}
        </div>
        {artifactSummaries.length === 0 ? (
          <div className="muted">No documents generated yet.</div>
        ) : (
          <DocList
            artifacts={artifactSummaries}
            selected={selected}
            approvals={approvals}
            onSelect={handleSelectArtifact}
          />
        )}
      </div>
      <div className="card">
        <strong>Preview</strong>
        <div className="doc-preview" aria-busy={loading || undefined}>
          {loading && (
            <div
              role="status"
              aria-live="polite"
              style={{
                position: "absolute",
                top: 6,
                right: 6,
                background: "var(--surface-1)",
                border: "1px solid var(--border)",
                borderRadius: 999,
                padding: "2px 8px",
                fontSize: 12,
                boxShadow: "var(--shadow-sm)",
              }}
            >
              <span aria-hidden>⏳</span> Generating…
            </div>
          )}
          {selected ? (
            selectedArtifact ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {selectedArtifact.content}
              </ReactMarkdown>
            ) : (
              <p className="doc-preview__placeholder">Loading latest version…</p>
            )
          ) : (
            <p className="doc-preview__placeholder">
              Select an artifact to preview it here.
            </p>
          )}
        </div>
        <div className="doc-preview__actions-row">
          <button
            className="btn"
            type="button"
            onClick={() => setPreviewModalOpen(true)}
            disabled={!selectedArtifact}
          >
            Expand
          </button>
        </div>
        {selected && (
          <div className="doc-preview__footer">
            <span
              className={
                selectedApproval?.approved
                  ? "doc-preview__status doc-preview__status--approved"
                  : "doc-preview__status doc-preview__status--pending"
              }
            >
              {selectedApproval?.approved
                ? `Approved • ${new Date(
                    selectedApproval.approved_at || "",
                  ).toLocaleString()}`
                : "Awaiting approval"}
            </span>
            <div className="doc-preview__actions">
              <button
                className="btn btn-primary"
                type="button"
                onClick={handleApproveSelected}
                disabled={
                  approvalBusy || !selected || selectedApproval?.approved === true
                }
              >
                {approvalBusy ? "Updating…" : "Approve"}
              </button>
              <button
                className="btn"
                type="button"
                onClick={handleRejectSelected}
                disabled={
                  approvalBusy || !selected || selectedApproval?.approved === false
                }
              >
                {approvalBusy ? "Updating…" : "Reject"}
              </button>
            </div>
          </div>
        )}
        <div style={{ marginTop: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <strong>Version History</strong>
            <button
              className="btn"
              onClick={async () => {
                if (!id) return;
                try {
                  const v = await listDocumentVersions(id);
                  setVersions(v);
                } catch (e: any) {
                  setError(e?.message || String(e));
                }
              }}
            >
              Refresh
            </button>
          </div>
          {(!versions || !selected || !versions.versions[selected]) && (
            <div className="muted">
              No versions yet for the selected document.
            </div>
          )}
          {versions && selected && versions.versions[selected] && (
            <ul>
              {versions.versions[selected]
                .slice()
                .reverse()
                .map((v) => (
                  <li key={v.version}>
                    v{v.version} — {new Date(v.created_at).toLocaleString()}{" "}
                    {previewVersion?.filename === selected &&
                    previewVersion?.version === v.version ? (
                      <span style={{ color: "#0a0", marginLeft: 8 }}>
                        (previewing)
                      </span>
                    ) : (
                      <button
                        className="btn"
                        style={{ marginLeft: 8 }}
                        onClick={() => onPreviewVersion(selected, v.version)}
                      >
                        Preview v{v.version}
                      </button>
                    )}
                  </li>
                ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );

  const DesignTab = (
    <div>
      {/* KPIs + Next Action */}
      <div
        className="grid-3"
        aria-label="Project KPIs"
        style={{ marginBottom: 12 }}
      >
        <Stat label="Requirements captured" value={String(reqCount)} />
        <Stat label="Documents generated" value={String(docCount || 0)} />
        <Stat label="Approved docs" value={String(approvedCount)} />
      </div>
      <NextAction
        message={
          sddArtifact
            ? "Answer open questions and apply them, then regenerate the SDD."
            : "No SDD yet. Generate documents from Requirements to create the initial SDD."
        }
        primary={
          sddArtifact
            ? {
                label: "Apply answers & Generate",
                onClick: applyAndGenerateFromDesign,
                variant: "primary",
              }
            : {
                label: "Generate with AI",
                onClick: onAIGenerateSmart,
                variant: "primary",
              }
        }
        secondary={[
          { label: "Regenerate SDD", onClick: onAIGenerateSDD },
          {
            label: "Open Requirements Chat",
            href: `/projects/${id}?tab=Requirements`,
          },
        ]}
      />
      <div className="card">
        <div className="section-title">Design</div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexWrap: "wrap",
          }}
        >
          <button className="btn" onClick={onAIGenerateSDD} disabled={loading}>
            {loading ? "Generating…" : "Regenerate SDD"}
          </button>
        </div>
        {!sddArtifact && (
          <div className="muted">
            No SDD generated yet. Generate documents from Requirements.
          </div>
        )}
        {sddArtifact && (
          <div
            style={{
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 12,
              marginTop: 8,
            }}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {sddArtifact.content}
            </ReactMarkdown>
          </div>
        )}
        <div
          style={{
            borderTop: "1px solid var(--border)",
            marginTop: 12,
            paddingTop: 12,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              flexWrap: "wrap",
            }}
          >
            <strong>Open Questions</strong>
            <button
              className="btn btn-primary"
              onClick={applyAndGenerateFromDesign}
              disabled={designGenerating || designQuestions.length === 0}
              aria-busy={designGenerating || undefined}
            >
              {designGenerating
                ? "Applying & Generating…"
                : "Apply answers & Generate"}
            </button>
            <button
              className="btn"
              onClick={applyDesignAnswersToContext}
              disabled={designGenerating || designQuestions.length === 0}
            >
              Apply answers
            </button>
            {qaNotice && <span className="muted">{qaNotice}</span>}
          </div>
          {designQuestions.length === 0 ? (
            <div className="muted" style={{ marginTop: 8 }}>
              No open questions found in the SDD.
            </div>
          ) : (
            <div style={{ display: "grid", gap: 12, marginTop: 8 }}>
              {designQuestions.map((q, i) => (
                <div key={i} className="card" style={{ padding: 12 }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 8,
                      marginBottom: 6,
                    }}
                  >
                    <strong>
                      Q{i + 1}. {q}
                    </strong>
                    <button className="btn" onClick={() => discussInChat(q)}>
                      Discuss in Chat
                    </button>
                  </div>
                  <label className="muted">Your answer</label>
                  <textarea
                    value={designAnswers[i] || ""}
                    onChange={(e) => onAnswerChange(i, e.target.value)}
                    rows={3}
                    style={{ width: "100%" }}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );

  const BacklogTab = (
    <div>
      {/* KPIs + Next Action */}
      <div
        className="grid-3"
        aria-label="Project KPIs"
        style={{ marginBottom: 12 }}
      >
        <Stat label="Requirements captured" value={String(reqCount)} />
        <Stat label="Documents generated" value={String(docCount || 0)} />
        <Stat label="Approved docs" value={String(approvedCount)} />
      </div>
      <NextAction
        message={
          includeBacklog
            ? "Generate or refresh backlog from the current context."
            : "Generate the backlog (Epics → Stories with Gherkin) with AI."
        }
        primary={{
          label: includeBacklog
            ? "AI Generate Backlog"
            : "Enable & Generate Backlog",
          onClick: onGenerateBacklogSmart,
          variant: "primary",
        }}
        secondary={[]}
      />
      <div className="card">
        <div className="section-title">Backlog</div>
        <div className="muted">
          Epics and Stories (with Gherkin) will appear here.
        </div>
      </div>
    </div>
  );

  const TestsTab = (
    <div>
      {/* KPIs + Next Action */}
      <div
        className="grid-3"
        aria-label="Project KPIs"
        style={{ marginBottom: 12 }}
      >
        <Stat label="Requirements captured" value={String(reqCount)} />
        <Stat label="Documents generated" value={String(docCount || 0)} />
        <Stat label="Approved docs" value={String(approvedCount)} />
      </div>
      <NextAction
        message={
          testPlanArtifact
            ? "Review the Test Plan and approve once ready."
            : "No Test Plan yet. Generate documents from Requirements."
        }
        primary={
          testPlanArtifact
            ? { label: "Regenerate Test Plan", onClick: onAIGenerateSmart }
            : {
                label: "Generate with AI",
                onClick: onAIGenerateSmart,
                variant: "primary",
              }
        }
        secondary={[]}
      />
      <div className="card">
        <div className="section-title">Tests</div>
        {!testPlanArtifact && (
          <div className="muted">
            No Test Plan generated yet. Generate documents from Requirements.
          </div>
        )}
        {testPlanArtifact && (
          <div
            style={{
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 12,
              marginTop: 8,
            }}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {testPlanArtifact.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );

  const SettingsTab = (
    <div style={{ display: "grid", gap: 12 }}>
      {/* KPIs + Next Action */}
      <div className="grid-3" aria-label="Project KPIs">
        <Stat label="Requirements captured" value={String(reqCount)} />
        <Stat label="Documents generated" value={String(docCount || 0)} />
        <Stat label="Approved docs" value={String(approvedCount)} />
      </div>
      <NextAction
        message="Save Stored Context updates and generate documents using it."
        primary={{
          label: "Generate with stored context",
          onClick: onGenerateWithStoredContext,
          variant: "primary",
        }}
        secondary={[]}
      />
      <div className="card">
        <strong>Stored Context</strong>
        <div className="muted" style={{ marginBottom: 8 }}>
          Saved context will be merged into document generation.
        </div>
        <label>Planning Summary</label>
        <textarea
          value={ctxPlanning}
          onChange={(e) => setCtxPlanning(e.target.value)}
          rows={3}
          style={{ width: "100%" }}
        />
        <label style={{ marginTop: 8, display: "block" }}>
          Requirements (one per line)
        </label>
        <textarea
          value={ctxRequirements}
          onChange={(e) => setCtxRequirements(e.target.value)}
          rows={6}
          style={{ width: "100%" }}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button className="btn" onClick={onSaveContext} disabled={savingCtx}>
            {savingCtx ? "Saving…" : "Save context"}
          </button>
          <button
            className="btn btn-primary"
            onClick={onGenerateWithStoredContext}
            disabled={loading}
          >
            {loading ? "Generating…" : "Generate with stored context"}
          </button>
        </div>
      </div>
      <div className="card">
        <strong>Impact Analysis</strong>
        <div className="muted" style={{ marginBottom: 8 }}>
          Enter FR IDs (e.g., FR-003, FR-011) separated by commas or new lines.
        </div>
        <textarea
          value={frInput}
          onChange={(e) => setFrInput(e.target.value)}
          rows={4}
          style={{ width: "100%" }}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button
            className="btn"
            onClick={onAnalyzeImpacts}
            disabled={analyzing || !frInput.trim()}
          >
            {analyzing ? "Analyzing…" : "Analyze"}
          </button>
        </div>
        {impacts && impacts.impacts && impacts.impacts.length > 0 && (
          <ul style={{ marginTop: 8 }}>
            {impacts.impacts.map((it, i) => (
              <li key={i}>
                <span style={{ color: "#666" }}>{it.kind}</span>: {it.name}{" "}
                <span style={{ color: "#999" }}>
                  ({Math.round(it.confidence * 100)}%)
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );

  const tabs = [
    { id: "Overview", label: "Overview", content: OverviewTab },
    { id: "Requirements", label: "Requirements", content: RequirementsTab },
    { id: "Design", label: "Design", content: DesignTab },
    { id: "Backlog", label: "Backlog", content: BacklogTab },
    { id: "Tests", label: "Tests", content: TestsTab },
    { id: "Docs", label: "Docs", content: DocsTab },
    { id: "Settings", label: "Settings", content: SettingsTab },
  ];

  const tabParam: string | undefined =
    typeof router.query.tab === "string" ? router.query.tab : undefined;
  const defaultTabId = tabParam
    ? (tabs.find((t) => t.id.toLowerCase() === tabParam.toLowerCase())?.id ??
      "Overview")
    : "Overview";

  return (
    <div>
      <p>
        <Link href="/projects">← Back to Projects</Link>
      </p>
      <h2>Project Workspace</h2>
      {loading && (
        <div className="badge" role="status">
          Loading…
        </div>
      )}
      {error && <p className="error">{error}</p>}
      {notice && <p className="notice">{notice}</p>}
      <section
        className="launch-hero launch-hero--wide project-workspace-hero"
        aria-label="Project workspace overview"
      >
        <div className="launch-hero__card">
          <div className="launch-hero__intro">
            <span className="launch-hero__badge badge">Project Workspace</span>
            <h1 className="launch-hero__title">
              {project?.name || "Concept to Deployment"}
            </h1>
            <p className="launch-hero__subtitle">{workspaceHeroSubtitle}</p>
            <ul className="launch-hero__list" aria-label="Workspace metrics">
              <li>
                <strong>Requirements captured</strong>
                <span>{reqCount}</span>
              </li>
              <li>
                <strong>Documents generated</strong>
                <span>{docCount}</span>
              </li>
              <li>
                <strong>Approved docs</strong>
                <span>{approvedCount}</span>
              </li>
            </ul>
            <div
              className="workspace-hero__actions"
              role="navigation"
              aria-label="Workspace quick links"
            >
              {workspaceQuickLinks.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="workspace-hero__action"
                  onClick={item.action}
                >
                  <span className="workspace-hero__action-label">{item.label}</span>
                  <span className="workspace-hero__action-desc">{item.description}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="launch-hero__panel">
            <span className="launch-hero__panel-label">Jump into a scenario</span>
            <div className="workspace-hero__scenarios">
              {heroScenarios.map((scenario) => (
                <button
                  key={scenario.label}
                  type="button"
                  className="workspace-hero__scenario"
                  onClick={() => routeToTab("Requirements", scenario.prompt)}
                >
                  <span className="workspace-hero__scenario-label">
                    {scenario.label}
                  </span>
                  <span className="workspace-hero__scenario-desc">
                    {scenario.description}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>
      <Tabs tabs={tabs} defaultTabId={defaultTabId} />
      <Modal
        open={previewModalOpen && !!selectedArtifact}
        onClose={() => setPreviewModalOpen(false)}
        title={selectedArtifact?.filename}
        size="xl"
        footer={
          selected ? (
            <div className="doc-preview__actions">
              <button
                className="btn btn-primary"
                type="button"
                onClick={handleApproveSelected}
                disabled={
                  approvalBusy || !selected || selectedApproval?.approved === true
                }
              >
                {approvalBusy ? "Updating…" : "Approve"}
              </button>
              <button
                className="btn"
                type="button"
                onClick={handleRejectSelected}
                disabled={
                  approvalBusy || !selected || selectedApproval?.approved === false
                }
              >
                {approvalBusy ? "Updating…" : "Reject"}
              </button>
            </div>
          ) : undefined
        }
      >
        {selectedArtifact ? (
          <div className="doc-preview doc-preview--modal">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {selectedArtifact.content}
            </ReactMarkdown>
          </div>
        ) : (
          <p className="doc-preview__placeholder">Select an artifact to preview.</p>
        )}
      </Modal>
    </div>
  );
}
