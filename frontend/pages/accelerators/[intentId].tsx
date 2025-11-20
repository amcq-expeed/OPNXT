import Link from "next/link";
import { useRouter } from "next/router";
import type { FormEvent } from "react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AcceleratorMessage,
  LaunchAcceleratorResponse,
  getAcceleratorSession,
  launchAcceleratorSession,
  postAcceleratorMessage,
  promoteAcceleratorSession,
  trackEvent,
  API_BASE_URL,
  getAccessToken,
  getAcceleratorPreviewHtml,
  getAcceleratorArtifactRaw,
  listAcceleratorPreviews,
  listChatModels,
  patchAcceleratorArtifact,
  runAcceleratorTests,
  ApiError,
  type AcceleratorArtifactEditRequest,
  type AcceleratorArtifactEditResponse,
  type AcceleratorPreview,
  type AcceleratorTestRunResponse,
  type ChatModelOption,
  downloadAcceleratorBundle,
  connectAcceleratorArtifactStream,
  type AcceleratorArtifactSnapshotEvent,
  type AcceleratorArtifactUpdatesEvent,
} from "../../lib/api";
import { useUserContext } from "../../lib/user-context";
import { getModelPreference, setModelPreference } from "../../lib/modelPreference";
import {
  getStoredAcceleratorSession,
  setStoredAcceleratorSession,
  removeStoredAcceleratorSession,
} from "../../lib/acceleratorSessionStorage";
import ChatComposer, {
  type ChatComposerConnectorToggle,
  type ChatComposerResourceMenuItem,
} from "../../components/chat/ChatComposer";
import MarkdownMessage from "../../components/MarkdownMessage";
import ResultBanner from "../../components/ResultBanner";
import {
  ProgressUpdate,
  PROGRESS_STAGE_LABELS,
  PROGRESS_STAGE_ORDER,
  convertProgressToPercent,
  formatBadgeLabel,
  formatProgressStage,
  extractStage,
  extractProgressValue,
  buildStageTimeline,
  interpretStreamUpdates,
} from '../../lib/acceleratorStream';

const DEFAULT_PAGE_SIZE = 50;

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

const INTENT_ALIASES: Record<string, string> = {
  "sdlc-docs": "generate-sdlc-doc",
  "generate-docs": "generate-sdlc-doc",
  "requirements-baseline": "requirements-baseline", // explicit for clarity
  "enhance-docs": "enhance-documentation",
};

const TONE_PLACEHOLDER_MAP: Record<ToneProfile, string> = {
  "warm-novice": "Describe what you need in plain language—I'm right beside you and will walk through each step.",
  "warm-expert": "Share the next deliverable you'd like me to generate or refine—I'll collaborate like a trusted peer.",
  concise: "Drop the specifics you need; I’ll respond concisely with actionable output.",
};

const TONE_LABELS: Record<ToneProfile, string> = {
  "warm-novice": "Novice mode",
  "warm-expert": "Expert mode",
  concise: "Concise mode",
};

const TONE_DESCRIPTIONS: Record<ToneProfile, string> = {
  "warm-novice": "Adds friendly affirmations, defines jargon, and explains why steps matter.",
  "warm-expert": "Keeps a collaborative tone, surfaces trade-offs, and moves quickly to decisions.",
  concise: "Prefers short confirmations and direct next actions without additional framing.",
};

const TONE_COACHING_TIPS: Record<ToneProfile, string[]> = {
  "warm-novice": [
    "Ask me to define acronyms or guardrails—I'll translate them into everyday language.",
    "If anything feels ambiguous, say 'break this down' and I'll outline the SDLC steps for you.",
  ],
  "warm-expert": [
    "Call out blockers or trade-offs and I'll surface mitigations tied to the SDLC plan.",
    "Need to pressure-test a requirement? Ask for pros/cons and I’ll benchmark against guardrails.",
  ],
  concise: [
    "Provide the key metric or decision you need—I'll respond with crisp next actions.",
    "Say 'give me the bullet list' anytime for a rapid executive-ready summary.",
  ],
};

const PERSONA_TONE_HINTS: Record<string, ToneProfile> = {
  executive: "concise",
  architect: "warm-expert",
  engineer: "warm-expert",
  developer: "warm-expert",
  qa: "warm-expert",
  tester: "warm-expert",
  product: "warm-novice",
};

type ToneProfile = "warm-novice" | "warm-expert" | "concise";

type SimplifiedArtifact = {
  filename: string;
  created_at?: string;
  version?: number;
  summary?: string;
  title?: string;
  type?: string;
  language?: string;
  meta?: Record<string, any>;
  messageId?: string | null;
  messageIds?: string[];
  diffSummary?: string | null;
  stage?: string | null;
  source?: string | null;
  frRefs?: string[];
  nfrRefs?: string[];
  gateStage?: string;
  progress?: number;
};

type ArtifactStreamItem = {
  filename?: string;
  version?: number;
  created_at?: string;
  meta?: Record<string, any> | null;
  [key: string]: any;
};

type ConversationMessage = AcceleratorMessage & {
  pending?: boolean;
  local?: boolean;
  origin?: "inline-edit" | "status" | "system";
};

export function formatTimeFromIso(iso?: string | null): string | null {
  if (!iso) return null;
  try {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return null;
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return null;
  }
}

type DiffSegment = {
  id: string;
  text: string;
  kind: "added" | "removed" | "context";
};

function parseDiffSummary(summary?: string | null): DiffSegment[] {
  if (!summary) return [];
  const segments: DiffSegment[] = [];
  const lines = summary
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
  lines.forEach((line, index) => {
    const kind: DiffSegment["kind"] = line.startsWith("+")
      ? "added"
      : line.startsWith("-")
        ? "removed"
        : "context";
    const text = kind === "context" ? line : line.slice(1).trim() || line;
    segments.push({
      id: `diff-${index}-${Math.random().toString(16).slice(2)}`,
      text,
      kind,
    });
  });
  return segments;
}

function extractMessageIds(sources: Array<any>, fallback?: string | null): string[] | undefined {
  const set = new Set<string>();
  sources.forEach((source) => {
    if (!source) return;
    const arrays = [source?.message_ids, source?.messageIds];
    arrays.forEach((value) => {
      if (!Array.isArray(value)) return;
      value.forEach((entry) => {
        if (typeof entry === "string") {
          const trimmed = entry.trim();
          if (trimmed) set.add(trimmed);
        }
      });
    });
    const singles = [source?.message_id, source?.messageId];
    singles.forEach((entry) => {
      if (typeof entry === "string") {
        const trimmed = entry.trim();
        if (trimmed) set.add(trimmed);
      }
    });
  });
  if (typeof fallback === "string") {
    const trimmed = fallback.trim();
    if (trimmed) set.add(trimmed);
  }
  return set.size ? Array.from(set) : undefined;
}

function chipClassForRole(role: string | undefined | null): string {
  switch (role) {
    case "assistant":
      return "accelerator-preview-card__chip accelerator-preview-card__chip--assistant";
    case "user":
      return "accelerator-preview-card__chip accelerator-preview-card__chip--user";
    default:
      return "accelerator-preview-card__chip accelerator-preview-card__chip--artifact";
  }
}

function generateClientMessageId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}


function buildTestCommandSummary(result: AcceleratorTestRunResponse | null): string {
  if (!result) return "";
  const parts = [result.status === "passed" ? "Tests passed" : result.status === "failed" ? "Tests failed" : "Tests completed"];
  if (typeof result.exit_code === "number") {
    parts.push(`exit code ${result.exit_code}`);
  }
  parts.push(`(${formatDuration(result.duration_ms)} elapsed)`);
  return parts.join(" • ");
}

const TEST_OUTPUT_MAX_LENGTH = 8000;

function normalizeTestOutput(value?: string | null): string {
  if (!value) return "";
  const trimmed = value.length > TEST_OUTPUT_MAX_LENGTH ? value.slice(value.length - TEST_OUTPUT_MAX_LENGTH) : value;
  return trimmed.trimEnd();
}

function testStatusToTone(status?: string | null): "success" | "warning" | "danger" | "info" {
  if (status === "passed") return "success";
  if (status === "failed") return "danger";
  if (status === "timeout") return "warning";
  return "info";
}

function formatDuration(ms: number): string {
  if (ms < 1000) return "<1s";
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) {
    return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

function formatElapsed(start: number | null, end?: number | null): string | null {
  if (!start) return null;
  const finish = end ?? Date.now();
  if (finish <= start) return "<1s";
  return formatDuration(finish - start);
}

function latestUserMessage(messages: ConversationMessage[]): string | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const candidate = messages[index];
    if (candidate?.role === "user" && !candidate?.pending) {
      const content = candidate?.content?.trim();
      if (content) return content;
    }
  }
  return null;
}

function extractHeadingFromMarkdown(markdown: string): string | null {
  const lines = markdown.split(/\r?\n/);
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;
    if (line.startsWith("#")) {
      const heading = line.replace(/^#+\s*/, "").trim();
      const normalized = normalizeTitleValue(heading);
      if (normalized) return normalized;
      continue;
    }
    if (line.length > 6) {
      return normalizeTitleValue(line);
    }
  }
  return null;
}

function normalizeTitleValue(value?: string | null): string | null {
  if (typeof value !== "string") return null;
  const collapsed = value.replace(/\s+/g, " ").trim();
  if (!collapsed) return null;
  return collapsed;
}

function normalizeForComparison(value?: string | null): string | null {
  const normalized = normalizeTitleValue(value);
  if (!normalized) return null;
  return normalized.replace(/[^a-z0-9]+/gi, " ").trim().replace(/\s+/g, " ").toLowerCase();
}

function isPromptEchoCandidate(candidateKey: string, promptKey: string): boolean {
  if (candidateKey === promptKey) return true;
  if (candidateKey.length >= promptKey.length && candidateKey.startsWith(promptKey)) {
    return candidateKey.length - promptKey.length <= 15;
  }
  if (promptKey.startsWith(candidateKey)) {
    return promptKey.length - candidateKey.length <= 15;
  }
  if (promptKey.length >= 24) {
    const cutoff = promptKey.slice(0, Math.floor(promptKey.length * 0.85));
    if (candidateKey.startsWith(cutoff)) return true;
  }
  return false;
}

function truncateTitle(value: string): string {
  return value.length > 140 ? `${value.slice(0, 137)}…` : value;
}

function chooseTitleCandidate(
  candidates: Array<string | null | undefined>,
  options?: { prompt?: string | null },
): string | null {
  const normalizedPromptKey = normalizeForComparison(options?.prompt ?? null);
  const seen = new Set<string>();
  for (const candidate of candidates) {
    const normalized = normalizeTitleValue(candidate);
    if (!normalized || normalized.length < 6) continue;
    const comparisonKey = normalizeForComparison(normalized);
    if (!comparisonKey) continue;
    if (normalizedPromptKey && isPromptEchoCandidate(comparisonKey, normalizedPromptKey)) continue;
    if (seen.has(comparisonKey)) continue;
    seen.add(comparisonKey);
    return truncateTitle(normalized);
  }
  return null;
}

function extractMetadataValue(meta: Record<string, any> | undefined | null, keys: string[]): string | null {
  if (!meta) return null;
  for (const key of keys) {
    const value = meta[key];
    const normalized = normalizeTitleValue(typeof value === "string" ? value : null);
    if (normalized) return normalized;
  }
  return null;
}

function decodeHtmlEntities(value: string): string {
  return value
    .replace(/&amp;/gi, "&")
    .replace(/&nbsp;/gi, " ")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'");
}

function stripHtmlTags(value: string): string {
  return value.replace(/<[^>]+>/g, " ");
}

function extractHeadingFromHtml(html: string): string | null {
  const headingMatch = html.match(/<h[1-3][^>]*>([\s\S]*?)<\/h[1-3]>/i);
  if (headingMatch && headingMatch[1]) {
    const text = normalizeTitleValue(decodeHtmlEntities(stripHtmlTags(headingMatch[1])));
    if (text) return text;
  }
  const paragraphMatch = html.match(/<p[^>]*>([\s\S]*?)<\/p>/i);
  if (paragraphMatch && paragraphMatch[1]) {
    const text = normalizeTitleValue(decodeHtmlEntities(stripHtmlTags(paragraphMatch[1])));
    if (text) return text;
  }
  const fallback = normalizeTitleValue(decodeHtmlEntities(stripHtmlTags(html)));
  if (fallback) {
    const sentence = fallback.split(/[.!?]/).find((segment) => segment.trim().length > 6);
    if (sentence) return sentence.trim();
    return fallback;
  }
  return null;
}

function prettifyFilename(filename?: string | null): string | null {
  if (!filename) return null;
  const withoutPath = filename.split(/[/\\]/).pop() ?? filename;
  const withoutExtension = withoutPath.replace(/\.[^.]+$/, "");
  if (!withoutExtension) return null;
  const words = withoutExtension
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .filter((word) => word.length > 0)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1));
  if (!words.length) return null;
  return words.join(" ");
}

function detectToneProfile(messages: ConversationMessage[], persona?: string | null): ToneProfile {
  const userMessage = latestUserMessage(messages);
  const personaHint = persona?.toLowerCase?.() ?? null;

  if (!userMessage) {
    if (personaHint) {
      const hinted = Object.entries(PERSONA_TONE_HINTS).find(([key]) => personaHint.includes(key));
      if (hinted) return hinted[1];
    }
    return "warm-novice";
  }

  const normalized = userMessage.toLowerCase();
  const noviceSignals = [
    /i'?m new/,
    /beginner/,
    /learning/,
    /can you explain/,
    /step[-\s]?by[-\s]?step/,
    /help me understand/,
    /walk me through/,
    /what does/,
    /how do i/,
    /not familiar/,
    /novice/,
  ];
  const conciseSignals = [
    /concise/,
    /short answer/,
    /tldr/,
    /just the code/,
    /no explanation/,
    /direct answer/,
    /expert mode/,
    /seasoned/,
    /skip the intro/,
  ];

  if (noviceSignals.some((pattern) => pattern.test(normalized))) return "warm-novice";
  if (conciseSignals.some((pattern) => pattern.test(normalized))) return "concise";

  const questionMarks = (normalized.match(/\?/g) ?? []).length;
  if (questionMarks >= 2) return "warm-novice";

  if (personaHint) {
    const hinted = Object.entries(PERSONA_TONE_HINTS).find(([key]) => personaHint.includes(key));
    if (hinted) return hinted[1];
  }

  return "warm-expert";
}

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
  const [previewMap, setPreviewMap] = useState<Record<string, AcceleratorPreview>>({});
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);
  const [selectedPreview, setSelectedPreview] = useState<AcceleratorPreview | null>(null);
  const [previewMode, setPreviewMode] = useState<"render" | "source">("render");
  const [previewHtml, setPreviewHtml] = useState<string>("");
  const [previewSource, setPreviewSource] = useState<string>("");
  const [previewHeight, setPreviewHeight] = useState<number>(720);
  const previewIframeRef = useRef<HTMLIFrameElement | null>(null);
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerExpanded, setDrawerExpanded] = useState(false);
  const [artifactMenuOpen, setArtifactMenuOpen] = useState(false);
  const artifactMenuContainerRef = useRef<HTMLDivElement | null>(null);
  const [previewActionsOpen, setPreviewActionsOpen] = useState(false);
  const previewActionsRef = useRef<HTMLDivElement | null>(null);
  const previewMainRegionRef = useRef<HTMLDivElement | null>(null);
  const messageNodeMapRef = useRef<Map<string, HTMLLIElement>>(new Map());
  const messageHighlightTimerRef = useRef<number | null>(null);
  const [toneProfile, setToneProfile] = useState<ToneProfile>("warm-novice");
  const [showToneMenu, setShowToneMenu] = useState<boolean>(false);
  const [modelOptions, setModelOptions] = useState<ChatModelOption[]>([]);
  const [modelLoading, setModelLoading] = useState<boolean>(false);
  const [modelError, setModelError] = useState<string | null>(null);
  const [selectedModelKey, setSelectedModelKey] = useState<string>(() => {
    const stored = getModelPreference();
    return stored ? `${stored.provider}:${stored.model}` : "adaptive:auto";
  });
  const [connectorSettings, setConnectorSettings] = useState({
    webSearch: true,
    research: false,
    extendedThinking: false,
    useStyle: false,
  });

  const [streaming, setStreaming] = useState<boolean>(false);
  const [heartbeatAt, setHeartbeatAt] = useState<number | null>(null);
  const [heartbeatStale, setHeartbeatStale] = useState<boolean>(false);
  const [reconnectingStream, setReconnectingStream] = useState<boolean>(false);
  const [connectionNotice, setConnectionNotice] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const heartbeatTimeoutMs = 15000;
  const artifactCountRef = useRef<number>(0);
  const [liveDraftPreview, setLiveDraftPreview] = useState<string>("");
  const [pendingMessages, setPendingMessages] = useState<ConversationMessage[]>([]);
  const [localMessages, setLocalMessages] = useState<ConversationMessage[]>([]);
  const [streamTimeoutReached, setStreamTimeoutReached] = useState<boolean>(false);
  const timeoutRef = useRef<number | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const [streamReconnectSeq, setStreamReconnectSeq] = useState<number>(0);
  const [progressUpdates, setProgressUpdates] = useState<ProgressUpdate[]>([]);
  const [allowProgress, setAllowProgress] = useState<boolean>(false);
  const [progressStartedAt, setProgressStartedAt] = useState<number | null>(null);
  const [progressCompletedAt, setProgressCompletedAt] = useState<number | null>(null);
  const [progressTicker, setProgressTicker] = useState<number>(0);
  const [editMode, setEditMode] = useState<boolean>(false);
  const [editDraft, setEditDraft] = useState<string>("");
  const [editSummary, setEditSummary] = useState<string>("");
  const [editSection, setEditSection] = useState<string>("full");
  const [editChangeDescription, setEditChangeDescription] = useState<string>("");
  const [autoSaveStatus, setAutoSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [autoSaveError, setAutoSaveError] = useState<string | null>(null);
  const [autoSavedAt, setAutoSavedAt] = useState<number | null>(null);
  const [savingEdit, setSavingEdit] = useState<boolean>(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [testRunResult, setTestRunResult] = useState<AcceleratorTestRunResponse | null>(null);
  const [testRunError, setTestRunError] = useState<string | null>(null);
  const [testRunning, setTestRunning] = useState<boolean>(false);
  const [testOutputVisible, setTestOutputVisible] = useState<boolean>(false);
  const [testOutputTab, setTestOutputTab] = useState<"stdout" | "stderr">("stdout");
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null);
  const autoSaveTimerRef = useRef<number | null>(null);
  const lastSavedPayloadRef = useRef<AcceleratorArtifactEditRequest | null>(null);
  const editMessageRef = useRef<string | undefined>(undefined);
  const [editLogPosted, setEditLogPosted] = useState<boolean>(false);

  const resetProgress = useCallback(() => {
    setProgressUpdates([]);
    setProgressStartedAt(null);
    setProgressCompletedAt(null);
    setProgressTicker(0);
  }, []);

  const pushProgressUpdate = useCallback(
    (
      message: string,
      kind: ProgressUpdate["kind"] = "info",
      stage?: string | null,
      progress?: number | null,
      timestampOverride?: number | null,
    ) => {
      if (!allowProgress) return;
      const trimmed = message?.trim();
      if (!trimmed) return;

      const normalizedStage = stage ? stage.trim().toLowerCase() : null;
      const normalizedProgress =
        typeof progress === "number" ? convertProgressToPercent(progress) : null;
      const eventTimestamp =
        typeof timestampOverride === "number" && Number.isFinite(timestampOverride)
          ? timestampOverride
          : Date.now();

      setProgressUpdates((prev) => {
        const last = prev[prev.length - 1];

        if (last && last.message === trimmed && last.kind === kind && last.stage === normalizedStage) {
          if (normalizedProgress !== null && last.progress !== normalizedProgress) {
            const updated: ProgressUpdate = {
              ...last,
              progress: normalizedProgress,
              timestamp: eventTimestamp,
            };
            if (kind === "success" || kind === "error") {
              setProgressCompletedAt(eventTimestamp);
            }
            return [...prev.slice(0, -1), updated];
          }
          return prev;
        }

        const entry: ProgressUpdate = {
          id: `progress-${eventTimestamp}-${Math.random().toString(16).slice(2)}`,
          message: trimmed,
          kind,
          timestamp: eventTimestamp,
          stage: normalizedStage,
          progress: normalizedProgress,
        };

        setProgressStartedAt((prevStart) => prevStart ?? eventTimestamp);
        if (kind === "success" || kind === "error") {
          setProgressCompletedAt(eventTimestamp);
        } else if (kind === "info") {
          setProgressCompletedAt(null);
        }

        const next = [...prev, entry];
        return next.length > 15 ? next.slice(next.length - 15) : next;
      });
    },
    [allowProgress],
  );

  useEffect(() => {
    if (!heartbeatAt) {
      setHeartbeatStale(false);
      if (!reconnectingStream) setConnectionNotice(null);
      return undefined;
    }
    const evaluate = () => {
      const stale = Date.now() - heartbeatAt > heartbeatTimeoutMs;
      setHeartbeatStale(stale);
      if (stale) {
        setConnectionNotice("Waiting for the live builder heartbeat…");
      } else if (!reconnectingStream) {
        setConnectionNotice(null);
      }
    };
    evaluate();
    const interval = window.setInterval(evaluate, Math.min(heartbeatTimeoutMs, 7500));
    return () => window.clearInterval(interval);
  }, [heartbeatAt, heartbeatTimeoutMs, reconnectingStream]);

  useEffect(() => {
    if (!heartbeatAt) return undefined;
    const timer = window.setTimeout(() => {
      if (heartbeatAt && Date.now() - heartbeatAt > heartbeatTimeoutMs) {
        setStreamError("Waiting for new artifacts. Generation is still in progress...");
        setStreamTimeoutReached(true);
      }
    }, heartbeatTimeoutMs);
    return () => window.clearTimeout(timer);
  }, [heartbeatAt]);

  useEffect(() => {
    if (!progressStartedAt || progressCompletedAt != null) {
      return () => {};
    }
    const interval = window.setInterval(() => setProgressTicker(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [progressStartedAt, progressCompletedAt]);

  const progressElapsedLabel = useMemo(
    () => formatElapsed(progressStartedAt, progressCompletedAt ?? undefined),
    [progressStartedAt, progressCompletedAt, progressTicker],
  );
  const progressInFlight = progressStartedAt != null && progressCompletedAt == null;
  const showProgressPanel = useMemo(
    () => progressUpdates.length > 0 && (progressInFlight || drawerExpanded),
    [progressUpdates.length, progressInFlight, drawerExpanded],
  );

  const rawIntentId = useMemo(() => {
    const raw = router.query.intentId;
    return typeof raw === "string" ? raw : null;
  }, [router.query.intentId]);

  const intentId = useMemo(() => {
    if (!rawIntentId) return null;
    const alias = INTENT_ALIASES[rawIntentId.toLowerCase()] || INTENT_ALIASES[rawIntentId] || null;
    return alias ?? rawIntentId;
  }, [rawIntentId]);

  const sessionId = useMemo(() => {
    const raw = router.query.session;
    return typeof raw === "string" ? raw : null;
  }, [router.query.session]);

  const [resumeSessionId, setResumeSessionId] = useState<string | null>(null);

  useEffect(() => {
    if (!router.isReady || !intentId) return;
    setResumeSessionId(getStoredAcceleratorSession(intentId));
  }, [intentId, router.isReady]);

  const source = useMemo(() => {
    const raw = router.query.source;
    return typeof raw === "string" && raw ? raw : "dashboard";
  }, [router.query.source]);

  useEffect(() => {
    if (!router.isReady || !rawIntentId || !intentId) return;
    const normalized = intentId;
    if (normalized === rawIntentId) return;
    const { intentId: _ignored, ...rest } = router.query;
    const params = new URLSearchParams();
    Object.entries(rest).forEach(([key, value]) => {
      if (Array.isArray(value)) {
        value.forEach((v) => params.append(key, v));
      } else if (value != null) {
        params.append(key, String(value));
      }
    });
    const search = params.toString();
    const asPath = `/accelerators/${encodeURIComponent(normalized)}${search ? `?${search}` : ""}`;
    void router.replace(
      {
        pathname: "/accelerators/[intentId]",
        query: { ...rest, intentId: normalized },
      },
      asPath,
      { shallow: true },
    );
  }, [router, rawIntentId, intentId]);

  useEffect(() => {
    if (!router.isReady || !intentId) return;
    let cancelled = false;

    const resolvedIntentId = intentId as string;

    const ensureStoredSessionParam = () => {
      if (sessionId || !resumeSessionId || !resolvedIntentId) return;
      const nextQuery: Record<string, string> = { intentId: resolvedIntentId, session: resumeSessionId };
      if (source) nextQuery.source = source;
      void router.replace({ pathname: "/accelerators/[intentId]", query: nextQuery }, undefined, { shallow: true });
    };

    ensureStoredSessionParam();

    const clearStaleSessionParam = async () => {
      if (cancelled) return;
      const nextQuery: Record<string, string> = {};
      Object.entries(router.query).forEach(([key, value]) => {
        if (key === "session") return;
        if (Array.isArray(value)) {
          if (value.length > 0) nextQuery[key] = String(value[0]);
        } else if (value != null) {
          nextQuery[key] = String(value);
        }
      });
      nextQuery.intentId = resolvedIntentId;
      await router.replace(
        { pathname: "/accelerators/[intentId]", query: nextQuery },
        undefined,
        { shallow: true },
      );
      removeStoredAcceleratorSession(resolvedIntentId);
      setResumeSessionId(null);
    };

    async function hydrate() {
      setLoading(true);
      setError(null);

      const persistSession = (session: LaunchAcceleratorResponse["session"], inferredIntentId: string) => {
        setStoredAcceleratorSession(inferredIntentId, session.session_id);
        setResumeSessionId(session.session_id);
      };

      const launchFreshSession = async () => {
        const launched = await launchAcceleratorSession(resolvedIntentId);
        if (!cancelled) {
          const nextQuery: Record<string, string> = {
            intentId: resolvedIntentId,
            session: launched.session.session_id,
          };
          if (source) nextQuery.source = source;
          void router.replace(
            { pathname: "/accelerators/[intentId]", query: nextQuery },
            undefined,
            { shallow: true },
          );
          persistSession(launched.session, resolvedIntentId);
        }
        return launched;
      };

      try {
        let result: LaunchAcceleratorResponse;
        if (sessionId) {
          try {
            result = await getAcceleratorSession(sessionId);
            persistSession(result.session, resolvedIntentId);
          } catch (err) {
            if (err instanceof ApiError && err.status === 404) {
              await clearStaleSessionParam();
              result = await launchFreshSession();
            } else {
              throw err;
            }
          }
        } else if (resumeSessionId) {
          try {
            result = await getAcceleratorSession(resumeSessionId);
            if (!cancelled) {
              const nextQuery: Record<string, string> = {
                intentId: resolvedIntentId,
                session: resumeSessionId,
              };
              if (source) nextQuery.source = source;
              void router.replace(
                { pathname: "/accelerators/[intentId]", query: nextQuery },
                undefined,
                { shallow: true },
              );
            }
            persistSession(result.session, resolvedIntentId);
          } catch (err) {
            removeStoredAcceleratorSession(resolvedIntentId);
            setResumeSessionId(null);
            result = await launchFreshSession();
          }
        } else {
          result = await launchFreshSession();
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
  const messages = useMemo(() => data?.messages ?? [], [data?.messages]);

  useEffect(() => {
    if (!session) return;
    const detected = detectToneProfile(messages, session.persona ?? persona ?? null);
    setToneProfile(detected);
  }, [messages, session, persona]);

  const latestAssistantMessageId = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const candidate = messages[index];
      if (candidate?.role === "assistant") {
        return candidate.message_id;
      }
    }
    return null;
  }, [messages]);
  const conversationMessages = useMemo<ConversationMessage[]>(() => {
    const confirmed = messages.map(
      (message) =>
        ({
          ...message,
          pending: false,
        }) as ConversationMessage,
    );
    const locals = localMessages.map((message) => ({ ...message, pending: false }));
    const timeline = [...confirmed, ...locals];
    const toTimestamp = (value?: string | null) => {
      if (!value) return 0;
      const date = new Date(value);
      const time = date.getTime();
      return Number.isNaN(time) ? 0 : time;
    };
    timeline.sort((a, b) => toTimestamp(a.created_at) - toTimestamp(b.created_at));
    return [...timeline, ...pendingMessages];
  }, [messages, localMessages, pendingMessages]);

  const messageMetaMap = useMemo(() => {
    const map = new Map<string, { index: number; message: AcceleratorMessage }>();
    messages.forEach((message, index) => {
      if (message?.message_id) {
        map.set(message.message_id, { index, message });
      }
    });
    localMessages.forEach((message, index) => {
      if (message?.message_id) {
        map.set(message.message_id, { index: messages.length + index, message });
      }
    });
    return map;
  }, [messages, localMessages]);

  useEffect(() => {
    if (allowProgress) return;
    const hasUserMessage = conversationMessages.some((message) => message.role === "user" && !message.pending);
    if (hasUserMessage) {
      setAllowProgress(true);
    }
  }, [conversationMessages, allowProgress]);

  useEffect(() => {
    if (!localMessages.length) return;
    const serverIds = new Set<string>();
    messages.forEach((message) => {
      if (typeof message?.message_id === "string" && message.message_id.trim()) {
        serverIds.add(message.message_id);
      }
    });
    if (serverIds.size === 0) return;
    setLocalMessages((prev) => prev.filter((message) => {
      if (!message?.message_id) return true;
      return !serverIds.has(message.message_id);
    }));
  }, [messages, localMessages.length]);

  const buildArtifactMessageMeta = useCallback(
    (artifact: SimplifiedArtifact | null | undefined) => {
      if (!artifact) return [] as Array<{ id: string; label: string; role: string }>;
      const source = artifact.messageIds ?? (artifact.messageId ? [artifact.messageId] : []);
      if (!source || source.length === 0) return [] as Array<{ id: string; label: string; role: string }>;
      const seen = new Set<string>();
      const items: Array<{ id: string; label: string; role: string }> = [];
      source.forEach((rawId) => {
        const id = typeof rawId === "string" ? rawId : null;
        if (!id || seen.has(id)) return;
        seen.add(id);
        const meta = messageMetaMap.get(id);
        if (!meta) return;
        const createdLabel = formatTimeFromIso(meta.message.created_at) ?? `Message ${meta.index + 1}`;
        items.push({
          id,
          label: createdLabel,
          role: meta.message.role,
        });
      });
      return items;
    },
    [messageMetaMap],
  );

  const focusMessageInConversation = useCallback(
    (messageId: string | null) => {
      if (!messageId || typeof window === "undefined") return;
      const node = messageNodeMapRef.current.get(messageId);
      if (!node) return;
      if (messageHighlightTimerRef.current) {
        window.clearTimeout(messageHighlightTimerRef.current);
        messageHighlightTimerRef.current = null;
      }
      setHighlightedMessageId(messageId);
      node.scrollIntoView({ behavior: "smooth", block: "center" });
      messageHighlightTimerRef.current = window.setTimeout(() => {
        setHighlightedMessageId((current) => (current === messageId ? null : current));
        messageHighlightTimerRef.current = null;
      }, 3200);
    },
    [],
  );

  useEffect(() => {
    return () => {
      if (messageHighlightTimerRef.current && typeof window !== "undefined") {
        window.clearTimeout(messageHighlightTimerRef.current);
        messageHighlightTimerRef.current = null;
      }
    };
  }, []);

  const handleJumpToMessage = useCallback(
    (messageId: string) => {
      focusMessageInConversation(messageId);
      setDrawerOpen(true);
    },
    [focusMessageInConversation],
  );

  const warmGuidanceActive = toneProfile !== "concise";
  const personaLabel = useMemo(() => formatPersonaLabel(session?.persona), [session?.persona]);
  const acceleratorModelOptions = useMemo<ChatModelOption[]>(() => {
    const raw = session?.metadata?.accelerator_models;
    if (!Array.isArray(raw)) return [];
    const mapped: ChatModelOption[] = [];
    raw.forEach((item) => {
      if (!item) return;
      const provider = typeof item.provider === "string" ? item.provider : null;
      const model = typeof item.model === "string" ? item.model : null;
      const label = typeof item.label === "string" ? item.label : null;
      if (!provider || !model || !label) return;
      mapped.push({
        provider,
        model,
        label,
        available: typeof item.available === "boolean" ? item.available : true,
        description: typeof item.description === "string" ? item.description : undefined,
        adaptive: typeof item.adaptive === "boolean" ? item.adaptive : undefined,
      });
    });
    return mapped;
  }, [session?.metadata]);

  useEffect(() => {
    const stored = getModelPreference();
    if (!stored) return;
    const key = `${stored.provider}:${stored.model}`;
    setSelectedModelKey(key);
  }, []);

  useEffect(() => {
    let active = true;
    async function hydrateModels() {
      setModelLoading(true);
      setModelError(null);
      try {
        if (acceleratorModelOptions.length > 0) {
          if (active) setModelOptions(acceleratorModelOptions);
          if (active) setModelLoading(false);
          return;
        }
        const options = await listChatModels();
        if (!active) return;
        setModelOptions(Array.isArray(options) ? options : []);
      } catch (e: any) {
        if (!active) return;
        setModelError(e?.message || "Unable to load models");
      } finally {
        if (active) setModelLoading(false);
      }
    }

    hydrateModels().catch(() => {
      if (active) setModelLoading(false);
    });

    return () => {
      active = false;
    };
  }, [acceleratorModelOptions]);

  const selectedModelOption = useMemo(() => {
    if (!modelOptions.length) return null;
    const found = modelOptions.find((opt) => `${opt.provider}:${opt.model}` === selectedModelKey && opt.available);
    if (found) return found;
    const firstAvailable = modelOptions.find((opt) => opt.available);
    return firstAvailable ?? modelOptions[0];
  }, [modelOptions, selectedModelKey]);

  useEffect(() => {
    if (!modelOptions.length) return;
    const desiredExists = modelOptions.some((opt) => `${opt.provider}:${opt.model}` === selectedModelKey);
    if (!desiredExists) {
      const fallback = modelOptions.find((opt) => opt.available) ?? modelOptions[0];
      if (fallback) {
        const key = `${fallback.provider}:${fallback.model}`;
        setSelectedModelKey(key);
        setModelPreference(fallback.provider, fallback.model);
      }
    }
  }, [modelOptions, selectedModelKey]);

  const normalizeArtifacts = useCallback((list: any): SimplifiedArtifact[] => {
    if (!Array.isArray(list)) return [];
    return list
      .map((item) => {
        if (!item) return null;
        const meta = item?.meta ?? {};
        const versionValue = item?.version ?? meta?.version;
        let parsedVersion: number | undefined;
        if (typeof versionValue === "number") parsedVersion = versionValue;
        else if (typeof versionValue === "string") {
          const numeric = Number(versionValue);
          parsedVersion = Number.isFinite(numeric) ? numeric : undefined;
        }
        const filename = typeof item?.filename === "string" ? item.filename : String(meta?.filename ?? "");
        if (!filename) return null;
        const summary =
          typeof meta?.summary === "string"
            ? meta.summary
            : typeof item?.summary === "string"
              ? item.summary
              : undefined;
        const title =
          typeof meta?.title === "string"
            ? meta.title
            : typeof item?.title === "string"
              ? item.title
              : undefined;
        const type =
          typeof item?.type === "string"
            ? item.type
            : typeof meta?.type === "string"
              ? meta.type
              : undefined;
        const language =
          typeof item?.language === "string"
            ? item.language
            : typeof meta?.language === "string"
              ? meta.language
              : undefined;
        let messageId =
          (typeof item?.message_id === "string" && item.message_id) ||
          (typeof meta?.message_id === "string" && meta.message_id) ||
          null;
        const messageIds = extractMessageIds([item, meta], messageId ?? undefined);
        if (!messageId && messageIds && messageIds.length > 0) {
          messageId = messageIds[0];
        }
        const diffSummary =
          typeof item?.diff === "string"
            ? item.diff
            : typeof meta?.diff_summary === "string"
              ? meta.diff_summary
              : null;
        const stage =
          (typeof item?.stage === "string" && item.stage) ||
          (typeof meta?.stage === "string" && meta.stage) ||
          null;
        const source =
          (typeof item?.source === "string" && item.source) ||
          (typeof meta?.source === "string" && meta.source) ||
          null;
        const frRefs = Array.isArray(meta?.fr_refs)
          ? (meta.fr_refs.filter((ref: unknown): ref is string => typeof ref === "string") as string[])
          : undefined;
        const nfrRefs = Array.isArray(meta?.nfr_refs)
          ? (meta.nfr_refs.filter((ref: unknown): ref is string => typeof ref === "string") as string[])
          : undefined;
        const gateStage = typeof meta?.gate_stage === "string" ? meta.gate_stage : undefined;
        const progress = typeof meta?.progress === "number" ? Math.max(0, Math.min(100, Math.round(meta.progress))) : undefined;

        return {
          filename,
          created_at: item?.created_at ?? meta?.created_at,
          version: parsedVersion,
          summary,
          title,
          type,
          language,
          meta,
          messageId,
          messageIds,
          diffSummary,
          stage,
          source,
          frRefs,
          nfrRefs,
          gateStage,
          progress,
        } satisfies SimplifiedArtifact;
      })
      .filter(Boolean) as SimplifiedArtifact[];
  }, []);

  const artifacts = useMemo(() => {
    const meta = session?.metadata;
    const list = (meta as any)?.artifacts;
    return normalizeArtifacts(list);
  }, [session?.metadata, normalizeArtifacts]);

  const mergeArtifacts = useCallback(
    (payload: any[]) => {
      const normalized = normalizeArtifacts(payload);
      if (!normalized.length) return;
      setLiveArtifacts((prev) => {
        const map = new Map<string, SimplifiedArtifact>();
        const mergeList = (list: SimplifiedArtifact[]) => {
          list.forEach((item) => {
            if (!item?.filename) return;
            const existing = map.get(item.filename);
            const mergedMeta = {
              ...(existing?.meta ?? {}),
              ...(item.meta ?? {}),
            };
            const mergedArtifact: SimplifiedArtifact = {
              ...(existing ?? {}),
              ...item,
              meta: mergedMeta,
            };
            map.set(item.filename, mergedArtifact);
          });
        };
        mergeList(artifacts);
        mergeList(prev);
        mergeList(normalized);
        return Array.from(map.values());
      });
    },
    [normalizeArtifacts, artifacts],
  );

  const applyPreviewCache = useCallback(
    (previews: AcceleratorPreview[], options?: { reset?: boolean }) => {
      if (!Array.isArray(previews)) {
        return;
      }
      setPreviewMap((prev) => {
        if (!previews.length && !options?.reset) {
          return prev;
        }
        if (!previews.length && options?.reset) {
          return {};
        }
        const next: Record<string, AcceleratorPreview> = options?.reset ? {} : { ...prev };
        previews.forEach((preview) => {
          const filename = typeof preview?.filename === "string" ? preview.filename : "";
          if (!filename) return;
          const prior = next[filename];
          const mergedMeta = {
            ...(prior?.meta ?? {}),
            ...(preview.meta ?? {}),
          };
          if (!mergedMeta.title) {
            mergedMeta.title = filename;
          }
          const content = typeof preview.content === "string" ? preview.content : prior?.content;
          next[filename] = {
            ...prior,
            ...preview,
            filename,
            meta: mergedMeta,
            content,
          } as AcceleratorPreview;
        });
        return next;
      });

      const previewArtifacts = previews
        .filter((preview) => typeof preview?.filename === "string" && preview.filename.trim().length > 0)
        .map((preview) => ({
          filename: preview.filename,
          version: preview.version,
          created_at: preview.created_at,
          meta: {
            ...(preview.meta ?? {}),
            title: preview.meta?.title ?? preview.filename,
            summary: preview.meta?.summary ?? preview.meta?.tagline,
            type: preview.meta?.type ?? preview.meta?.kind ?? "preview",
            language: preview.meta?.language,
            iframe_url: preview.meta?.iframe_url,
          },
        }));
      if (previewArtifacts.length) {
        mergeArtifacts(previewArtifacts);
      }
    },
    [mergeArtifacts],
  );

  const refreshPreviews = useCallback(
    async (options?: { reset?: boolean; cancelledRef?: { current: boolean } }) => {
      const sessionId = session?.session_id;
      if (!sessionId) {
        if (options?.reset) {
          setPreviewMap({});
        }
        return;
      }
      try {
        const previews = await listAcceleratorPreviews(sessionId);
        if (options?.cancelledRef?.current) return;
        applyPreviewCache(previews, options);
      } catch (err) {
        console.error("accelerator_preview_refresh_failed", err);
      }
    },
    [session?.session_id, applyPreviewCache],
  );

  const displayArtifacts = liveArtifacts.length ? liveArtifacts : artifacts;
  const artifactCount = displayArtifacts.length;
  const defaultArtifactId = useMemo(() => {
    if (!displayArtifacts.length) return null;
    const preferred = displayArtifacts.find((artifact) => {
      if (!artifact) return false;
      const filename = artifact.filename?.toLowerCase() ?? "";
      const metaType = typeof artifact.meta?.type === "string" ? artifact.meta.type.toLowerCase() : "";
      const hasIframe = Boolean(artifact.meta?.iframe_url);
      const isPreviewType = artifact.type === "preview" || metaType === "preview";
      const isHtmlFile = filename.endsWith(".html") || filename.endsWith(".htm");
      const isHtmlLanguage =
        typeof artifact.meta?.language === "string" && artifact.meta.language.toLowerCase() === "html";
      return isPreviewType || hasIframe || isHtmlFile || isHtmlLanguage;
    });
    return (preferred ?? displayArtifacts[0])?.filename ?? null;
  }, [displayArtifacts]);
  useEffect(() => {
    const previousCount = artifactCountRef.current;
    artifactCountRef.current = artifactCount;

    if (artifactCount > previousCount) {
      setDrawerOpen(true);
      setLiveDraftPreview("");
    }

    if (artifactCount > 0) {
      setStreamTimeoutReached(false);
      setStreamError(null);
    }
  }, [artifactCount]);

  useEffect(() => {
    requestAnimationFrame(() => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }));
  }, [conversationMessages.length]);

  useEffect(() => {
    if (!localMessages.length) return;
    const serverIds = new Set<string>();
    messages.forEach((message) => {
      if (typeof message?.message_id === "string" && message.message_id.trim()) {
        serverIds.add(message.message_id);
      }
    });
    if (serverIds.size === 0) return;
    setLocalMessages((prev) => prev.filter((message) => {
      if (!message?.message_id) return true;
      return !serverIds.has(message.message_id);
    }));
  }, [messages, localMessages.length]);

  useEffect(() => {
    if (!session?.session_id) return;
    let cancelled = false;
    let streamActive = false;
    artifactCountRef.current = Math.max(artifactCountRef.current, 0);

    if (timeoutRef.current) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    timeoutRef.current = window.setTimeout(() => {
      if (!cancelled && artifactCountRef.current === 0) {
        setStreamError("Still assembling artifacts. You can retry generation or open the project workspace to continue manually.");
        setStreamTimeoutReached(true);
      }
    }, 30000);

    const updateLiveArtifacts = (artifactsPayload: any[]) => {
      const normalized = normalizeArtifacts(artifactsPayload);
      if (!normalized.length) return;
      setLiveArtifacts((prev) => {
        const map = new Map<string, SimplifiedArtifact>();
        const mergeList = (list: SimplifiedArtifact[]) => {
          list.forEach((item) => {
            if (!item?.filename) return;
            const existing = map.get(item.filename);
            map.set(item.filename, existing ? { ...existing, ...item } : item);
          });
        };
        mergeList(artifacts);
        mergeList(prev);
        mergeList(normalized);
        return Array.from(map.values());
      });
    };

    const handleSnapshot = (event: AcceleratorArtifactSnapshotEvent) => {
      if (cancelled) return;
      streamActive = false;
      setStreaming(false);
      setLiveDraftPreview("");
      setDrawerOpen(true);
      if (Array.isArray(event.artifacts) && event.artifacts.length > 0) {
        pushProgressUpdate("Artifacts ready.", "success", "ready", 1);
      }
      updateLiveArtifacts(event.artifacts ?? []);
      const snapshotPreviews = (event.artifacts ?? [])
        .filter((artifact: any) => typeof artifact?.filename === "string")
        .map((artifact: any) => ({
          filename: artifact.filename,
          version: artifact.version ?? artifact.meta?.version,
          created_at: artifact.created_at,
          content: artifact.meta?.content,
          meta: artifact.meta ?? {},
        }));
      if (snapshotPreviews.length) {
        applyPreviewCache(snapshotPreviews);
      }
    };

    const handleUpdates = (event: AcceleratorArtifactUpdatesEvent) => {
      if (cancelled) return;
      const updates = Array.isArray(event.updates) ? event.updates : [];
      if (updates.length) {
        const interpretation = interpretStreamUpdates(updates);
        interpretation.progressEntries.forEach((entry) => {
          pushProgressUpdate(entry.message, entry.kind, entry.stage, entry.progress, entry.timestamp ?? null);
        });

        if (interpretation.streamError) {
          setStreamError(interpretation.streamError);
        }

        if (interpretation.actionStatus) {
          setActionStatus(interpretation.actionStatus);
        }

        if (typeof interpretation.nextLiveDraft === "string") {
          setLiveDraftPreview(interpretation.nextLiveDraft);
        }

        if (interpretation.clearLiveDraft) {
          setLiveDraftPreview("");
        }

        if (interpretation.activateStream && !streamActive) {
          streamActive = true;
          setStreaming(true);
        }

        if (interpretation.stopStream && streamActive) {
          streamActive = false;
          setStreaming(false);
        }

        if (interpretation.openDrawer) {
          setDrawerOpen(true);
        }
      }

      const recentArtifacts = (event as any).artifacts ?? event.updates ?? [];
      updateLiveArtifacts(recentArtifacts);
      const previewCandidates = recentArtifacts
        .filter((artifact: any) => typeof artifact?.filename === "string")
        .map((artifact: any) => ({
          filename: artifact.filename,
          version: artifact.version ?? artifact.meta?.version,
          created_at: artifact.created_at,
          content: artifact.meta?.content,
          meta: artifact.meta ?? {},
        }));
      if (previewCandidates.length) {
        applyPreviewCache(previewCandidates);
      }
    };

    const disconnect = connectAcceleratorArtifactStream(
      session.session_id,
      {
        onSnapshot: handleSnapshot,
        onUpdates: handleUpdates,
        onHeartbeat: () => {
          if (cancelled) return;
          setHeartbeatAt(Date.now());
          setStreamError(null);
          setConnectionNotice(null);
          setHeartbeatStale(false);
        },
        onStatus: (status, meta) => {
          if (cancelled) return;
          switch (status) {
            case "connecting":
              setReconnectingStream(true);
              setConnectionNotice("Connecting to the live builder…");
              setStreamError(null);
              streamActive = false;
              setStreaming(false);
              break;
            case "open":
              reconnectAttemptsRef.current = 0;
              setReconnectingStream(false);
              setConnectionNotice(null);
              setStreamError(null);
              setStreamTimeoutReached(false);
              break;
            case "error": {
              const attempt = (meta?.attempt ?? reconnectAttemptsRef.current) + 1;
              reconnectAttemptsRef.current = attempt;
              setStreamError("We lost connection to the artifact stream. Retrying…");
              setConnectionNotice("Lost contact with live builder. Retrying…");
              setStreaming(false);
              setReconnectingStream(true);
              if (attempt === 1) {
                pushProgressUpdate("Lost connection to live builder. Retrying…", "error", "analysis", 0.05);
              }
              break;
            }
            case "closed":
              setStreaming(false);
              setReconnectingStream(true);
              setConnectionNotice("Live builder connection closed. Reconnecting…");
              if (!streamActive) {
                pushProgressUpdate("Live builder paused. Reconnecting…", "info", "analysis", 0.08);
              }
              break;
            default:
              break;
          }
        },
      },
      {
        initialRevision: session.metadata?.artifact_revision ?? 0,
      },
    );

    return () => {
      cancelled = true;
      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      disconnect();
    };
  }, [session?.session_id, normalizeArtifacts, artifacts, streamReconnectSeq, pushProgressUpdate]);

  const handleRetryStream = useCallback(() => {
    if (timeoutRef.current) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    if (reconnectTimerRef.current) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    reconnectAttemptsRef.current = 0;
    artifactCountRef.current = 0;
    setStreamError(null);
    setStreamTimeoutReached(false);
    setLiveDraftPreview("");
    setProgressUpdates([]);
    setStreamReconnectSeq((prev) => prev + 1);
    pushProgressUpdate("Retrying live builder…", "info");
  }, [pushProgressUpdate]);

  const handleOpenWorkspace = useCallback(() => {
    if (!promotionProjectId) return;
    void router.push(`/projects/${encodeURIComponent(promotionProjectId)}?tab=Requirements`);
  }, [promotionProjectId, router]);

  const artifactDetails = useMemo(() => {
    const map = new Map<string, SimplifiedArtifact>();
    for (const item of displayArtifacts) {
      if (!item.filename) continue;
      map.set(item.filename, item);
    }
    return map;
  }, [displayArtifacts]);

  const codeArtifacts = useMemo(() => displayArtifacts.filter((artifact) => artifact.type === "code"), [displayArtifacts]);
  const testArtifact = useMemo(() => {
    const byType = displayArtifacts.find((artifact) => artifact.type === "test");
    if (byType) return byType;
    const fileMatch = displayArtifacts.find((artifact) =>
      artifact.filename?.toLowerCase().includes("test"),
    );
    return fileMatch ?? null;
  }, [displayArtifacts]);
  const testArtifactPath = useMemo(() => {
    if (!testArtifact) return null;
    const fromMeta = typeof testArtifact.meta?.path === "string" ? testArtifact.meta.path.trim() : null;
    if (fromMeta) return fromMeta;
    return testArtifact.filename ?? null;
  }, [testArtifact]);
  const canRunTests = Boolean(session?.session_id && testArtifactPath);

  useEffect(() => {
    setTestRunResult(null);
    setTestRunError(null);
    setTestOutputVisible(false);
    setTestRunning(false);
    setTestOutputTab("stdout");
  }, [session?.session_id, testArtifactPath]);

  const handleRunTests = useCallback(async () => {
    if (!session?.session_id || !canRunTests || !testArtifactPath) {
      return;
    }
    setTestRunning(true);
    setTestRunError(null);
    setTestRunResult(null);
    setTestOutputVisible(true);
    setTestOutputTab("stdout");
    pushProgressUpdate("Running inline tests…", "info", "validation", 90);
    try {
      trackEvent("accelerator_inline_tests_run", {
        sessionId: session.session_id,
        intentId: intent?.intent_id,
        testPath: testArtifactPath,
      });
      const result = await runAcceleratorTests(session.session_id, {
        test_path: testArtifactPath,
      });
      setTestRunResult(result);
      const summary =
        result.status === "passed"
          ? "Inline tests passed."
          : result.status === "failed"
            ? "Inline tests failed."
            : result.status === "timeout"
              ? "Inline tests timed out."
              : "Inline tests completed.";
      const kind = result.status === "passed" ? "success" : result.status === "failed" ? "error" : "info";
      const stage = result.status === "passed" ? "ready" : "validation";
      const percent = result.status === "passed" ? 100 : 95;
      pushProgressUpdate(summary, kind, stage, percent);
    } catch (err: unknown) {
      let message = "Unable to run tests.";
      if (err instanceof ApiError) {
        message = err.message || message;
      } else if (err instanceof Error && err.message) {
        message = err.message;
      }
      setTestRunError(message);
      pushProgressUpdate(message, "error", "validation", 95);
    } finally {
      setTestRunning(false);
    }
  }, [session?.session_id, canRunTests, testArtifactPath, pushProgressUpdate, trackEvent, intent?.intent_id]);

  useEffect(() => {
    if (artifactCount === 0) {
      setSelectedArtifactId(null);
      setSelectedPreview(null);
      setPreviewHtml("");
      setPreviewSource("");
      return;
    }
    if (!selectedArtifactId || !artifactDetails.has(selectedArtifactId)) {
      setSelectedArtifactId(defaultArtifactId);
    }
  }, [displayArtifacts, artifactCount, selectedArtifactId, artifactDetails, defaultArtifactId]);

  useEffect(() => {
    if (artifactCount === 0 && drawerOpen) {
      setDrawerOpen(false);
      setDrawerExpanded(false);
      setArtifactMenuOpen(false);
      setPreviewActionsOpen(false);
    }
  }, [artifactCount, drawerOpen]);

  useEffect(() => {
    if (!drawerOpen) {
      setPreviewActionsOpen(false);
    }
  }, [drawerOpen]);

  useEffect(() => {
    if (!artifactMenuOpen) return;
    const handler = (event: MouseEvent) => {
      if (!artifactMenuContainerRef.current) return;
      if (!artifactMenuContainerRef.current.contains(event.target as Node)) {
        setArtifactMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => {
      document.removeEventListener("mousedown", handler);
    };
  }, [artifactMenuOpen]);

  useEffect(() => {
    if (!previewActionsOpen) return;
    const handler = (event: MouseEvent) => {
      if (!previewActionsRef.current) return;
      if (!previewActionsRef.current.contains(event.target as Node)) {
        setPreviewActionsOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => {
      document.removeEventListener("mousedown", handler);
    };
  }, [previewActionsOpen]);

  const resourceMenuConfig = useMemo(() => {
    if (!session) return undefined;
    const items: ChatComposerResourceMenuItem[] = [
      {
        id: "project",
        label: "Use a project",
        icon: "📁",
        onSelect: () =>
          setDraft((value) => `${value ? `${value}\n\n` : ""}Please scaffold a starter project.`),
      },
      { id: "drive", label: "Add from Google Drive", icon: "📂", disabled: true },
      { id: "github", label: "Add from GitHub", icon: "🐙", disabled: true },
      { id: "screenshot", label: "Take a screenshot", icon: "📸", disabled: true },
      { id: "upload", label: "Upload a file", icon: "⤴", disabled: true },
    ];
    return {
      accountLabel: user?.email ?? "me",
      searchPlaceholder: "Search menu",
      items,
    };
  }, [session, user?.email, setDraft]);

  const connectorToggles = useMemo<ChatComposerConnectorToggle[]>(
    () => [
      {
        id: "drive",
        label: "Drive search",
        icon: "🟩",
        value: false,
        disabled: true,
        onChange: () => {},
      },
      {
        id: "web",
        label: "Web search",
        icon: "🌐",
        value: connectorSettings.webSearch,
        onChange: (next) => setConnectorSettings((prev) => ({ ...prev, webSearch: next })),
      },
      {
        id: "research",
        label: "Research",
        icon: "🔬",
        value: connectorSettings.research,
        onChange: (next) => setConnectorSettings((prev) => ({ ...prev, research: next })),
      },
      {
        id: "extended",
        label: "Extended thinking",
        icon: "🧠",
        value: connectorSettings.extendedThinking,
        onChange: (next) => setConnectorSettings((prev) => ({ ...prev, extendedThinking: next })),
      },
      {
        id: "style",
        label: "Use style",
        icon: "🎨",
        value: connectorSettings.useStyle,
        onChange: (next) => setConnectorSettings((prev) => ({ ...prev, useStyle: next })),
      },
    ],
    [connectorSettings],
  );

  const connectorMenuConfig = useMemo(() => {
    if (!session) return undefined;
    const items: ChatComposerResourceMenuItem[] = [
      {
        id: "calendar",
        label: "Calendar search",
        icon: "📅",
        accessoryLabel: "Connect ↗",
        disabled: true,
      },
      {
        id: "gmail",
        label: "Gmail search",
        icon: "📧",
        accessoryLabel: "Connect ↗",
        disabled: true,
      },
    ];
    return {
      headerLabel: "Manage connectors",
      addConnectorsLabel: "Add connectors",
      items,
      toggles: connectorToggles,
      searchPlaceholder: "Search connectors",
    };
  }, [session, connectorToggles]);

  const extendedThinkingConfig = useMemo(
    () =>
      session
        ? {
            value: connectorSettings.extendedThinking,
            onToggle: (next: boolean) =>
              setConnectorSettings((prev) => ({ ...prev, extendedThinking: next })),
            icon: "🧠",
            tooltip: "Extended thinking",
          }
        : undefined,
    [session, connectorSettings.extendedThinking],
  );

  useEffect(() => {
    if (!session?.session_id) return;
    trackEvent("accelerator_tone_detected", {
      sessionId: session.session_id,
      tone: toneProfile,
    });
  }, [session?.session_id, toneProfile]);

  const activeArtifact = selectedArtifactId ? artifactDetails.get(selectedArtifactId) ?? null : null;
  const activeArtifactMessages = useMemo(() => buildArtifactMessageMeta(activeArtifact), [activeArtifact, buildArtifactMessageMeta]);
  const activeArtifactCreatedAt = useMemo(() => formatTimeFromIso(activeArtifact?.created_at ?? activeArtifact?.meta?.created_at), [activeArtifact?.created_at, activeArtifact?.meta?.created_at]);
  const activeArtifactDiffSegments = useMemo(() => parseDiffSummary(activeArtifact?.diffSummary ?? (typeof activeArtifact?.meta?.diff_summary === "string" ? activeArtifact.meta.diff_summary : undefined)), [activeArtifact?.diffSummary, activeArtifact?.meta?.diff_summary]);

  const handleSelectArtifact = useCallback(
    (filename: string | null, options?: { forceRefresh?: boolean }) => {
      if (!filename) {
        setSelectedArtifactId(null);
        setSelectedPreview(null);
        setPreviewHtml("");
        setPreviewSource("");
        return;
      }
      setSelectedArtifactId(filename);
      setPreviewMode("render");
      setDrawerOpen(true);
      const nextArtifact = artifactDetails.get(filename);
      if (nextArtifact) {
        const linked = buildArtifactMessageMeta(nextArtifact);
        if (linked.length > 0) {
          focusMessageInConversation(linked[0].id);
        }
      }
      if (options?.forceRefresh && session?.session_id) {
        void refreshPreviews({ cancelledRef: { current: false } });
      }
    },
    [artifactDetails, focusMessageInConversation, session?.session_id, refreshPreviews],
  );

  useEffect(() => {
    if (!session?.session_id) {
      setPreviewMap({});
      return;
    }
    const cancelledRef = { current: false };
    void refreshPreviews({ reset: true, cancelledRef });
    return () => {
      cancelledRef.current = true;
    };
  }, [session?.session_id, refreshPreviews]);

  useEffect(() => {
    if (!selectedArtifactId || !session?.session_id) {
      setSelectedPreview(null);
      setPreviewHtml("");
      setPreviewSource("");
      return;
    }

    let cancelled = false;
    const preview = previewMap[selectedArtifactId] ?? null;
    setSelectedPreview(preview ?? null);
    const fallbackContent = preview?.content ?? "";
    setPreviewHtml(fallbackContent);
    setPreviewSource(fallbackContent);

    if (!preview?.content) {
      void getAcceleratorPreviewHtml(session.session_id, selectedArtifactId)
        .then((html) => {
          if (cancelled) return;
          setPreviewHtml(html);
          applyPreviewCache(
            [
              {
                filename: selectedArtifactId,
                version: activeArtifact?.version ?? preview?.version ?? 1,
                created_at: activeArtifact?.created_at ?? preview?.created_at ?? new Date().toISOString(),
                meta: {
                  ...(activeArtifact?.meta ?? {}),
                  ...(preview?.meta ?? {}),
                },
                content: html,
              },
            ],
          );
        })
        .catch((err) => console.error("fetch_preview_html_failed", err));
    }

    void getAcceleratorArtifactRaw(session.session_id, selectedArtifactId)
      .then((text) => {
        if (cancelled) return;
        setPreviewSource(text);
      })
      .catch((err) => {
        console.error("fetch_preview_raw_failed", err);
        setPreviewSource((prev) => prev || fallbackContent);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedArtifactId, session?.session_id, previewMap, activeArtifact]);

  const selectedPreviewMeta = useMemo(() => selectedPreview?.meta ?? {}, [selectedPreview]);
  const selectedIsHtml = useMemo(() => {
    const ext = selectedPreview?.filename?.split(".").pop()?.toLowerCase();
    if (ext === "html") return true;
    const language = typeof selectedPreviewMeta?.language === "string" ? selectedPreviewMeta.language : undefined;
    return language?.toLowerCase() === "html";
  }, [selectedPreview, selectedPreviewMeta]);

  const hasRenderContent = previewHtml.trim().length > 0;
  const hasSourceContent = previewSource.trim().length > 0;
  const renderContent = useMemo(() => {
    if (selectedIsHtml) return previewHtml;
    const combined = previewHtml || previewSource;
    if (!combined) return "";
    const trimmed = combined.trim();
    if (!trimmed) return "";
    const mimicPromptEcho = activeArtifact?.meta?.includePrompt ?? false;
    if (mimicPromptEcho) return trimmed;
    const promptDividerIndex = trimmed.indexOf("---\nUser prompt");
    if (promptDividerIndex > 0) {
      return trimmed.slice(0, promptDividerIndex).trimEnd();
    }
    return trimmed;
  }, [selectedIsHtml, previewHtml, previewSource, activeArtifact?.meta?.includePrompt]);
  const sourceText = hasSourceContent ? previewSource : previewHtml;

  useEffect(() => {
    if (!selectedPreview || editMode) return;
    const meta = selectedPreview.meta ?? {};
    setEditDraft(previewMode === "source" ? sourceText : previewHtml);
    setEditSummary(typeof meta.summary === "string" ? meta.summary : "");
    setEditSection(typeof meta.section === "string" ? meta.section : "");
    setEditChangeDescription(typeof meta.change_description === "string" ? meta.change_description : "");
    setEditError(null);
  }, [editMode, previewHtml, sourceText, selectedPreview?.meta, previewMode, selectedPreview]);
  const diffSummary = useMemo(() => {
    const artifactDiff = activeArtifact?.diffSummary;
    const raw = typeof selectedPreviewMeta?.diff_summary === "string" && selectedPreviewMeta.diff_summary
      ? selectedPreviewMeta.diff_summary
      : artifactDiff ?? null;
    if (typeof raw !== "string") return null;
    const trimmed = raw.trim();
    return trimmed.length ? trimmed : null;
  }, [selectedPreviewMeta, activeArtifact?.diffSummary]);

  const htmlIframeUrl = useMemo(() => {
    if (!selectedPreview || previewMode !== "render") return null;
    const iframePath = selectedPreviewMeta?.iframe_url;
    if (typeof iframePath !== "string" || !iframePath) return null;
    if (session?.session_id) {
      return `${API_BASE_URL}${iframePath}`;
    }
    return null;
  }, [selectedPreview, selectedPreviewMeta, previewMode, session?.session_id]);

  useEffect(() => {
    if (previewMode !== "render" || !htmlIframeUrl) return;
    const iframe = previewIframeRef.current;
    if (!iframe) return;
    const listener = (event: MessageEvent) => {
      if (!event.data || typeof event.data !== "object") return;
      if (event.data.type === "accelerator_preview_height" && typeof event.data.height === "number") {
        const nextHeight = Math.min(Math.max(event.data.height, 520), 2200);
        setPreviewHeight(nextHeight);
      }
    };
    window.addEventListener("message", listener);
    const handleLoad = () => {
      try {
        iframe.contentWindow?.postMessage({ type: "accelerator_preview_measure" }, "*");
      } catch (err) {
        console.error("iframe_measure_failed", err);
      }
    };
    iframe.addEventListener("load", handleLoad);
    if (iframe.contentDocument?.readyState === "complete") {
      handleLoad();
    }
    return () => {
      window.removeEventListener("message", listener);
      iframe.removeEventListener("load", handleLoad);
    };
  }, [previewMode, htmlIframeUrl, selectedPreview]);

  const frameHeight = useMemo(() => {
    if (previewMode !== "render" || !selectedIsHtml) return null;
    if (htmlIframeUrl) return Math.max(previewHeight, 520);
    if (previewHtml.trim()) return Math.max(previewHeight, 840);
    return 640;
  }, [previewMode, selectedIsHtml, htmlIframeUrl, previewHeight, previewHtml]);

  const displayedArtifactMetadata = useMemo(() => {
    const fromArtifact = activeArtifact?.meta ?? {};
    const fromPreview = selectedPreview?.meta ?? {};
    return { ...fromPreview, ...fromArtifact };
  }, [activeArtifact?.meta, selectedPreview?.meta]);

  const fallbackContentTitle = useMemo(() => {
    if (previewHtml) {
      const heading = extractHeadingFromHtml(previewHtml);
      if (heading) return heading;
    }
    if (previewSource) {
      const heading = extractHeadingFromMarkdown(previewSource);
      if (heading) return heading;
    }
    return null;
  }, [previewHtml, previewSource]);

  const fallbackIntentTitle = useMemo(() => {
    const intentHint = normalizeTitleValue(intent?.title);
    if (intentHint) return intentHint;
    const sessionName = normalizeTitleValue(session?.metadata?.session_name);
    if (sessionName) return sessionName;
    const docType = extractMetadataValue(displayedArtifactMetadata, ["document_type", "doc_type", "artifact_type"]);
    if (docType) return docType;
    return null;
  }, [intent?.title, session?.metadata?.session_name, displayedArtifactMetadata]);

  const fallbackFilenameTitle = useMemo(
    () =>
      prettifyFilename(activeArtifact?.filename) ||
      prettifyFilename(selectedPreview?.filename) ||
      null,
    [activeArtifact?.filename, selectedPreview?.filename],
  );

  const metadataTitle = useMemo(
    () => extractMetadataValue(displayedArtifactMetadata, ["title", "document_title", "name", "artifact_title"]) ?? normalizeTitleValue(activeArtifact?.title),
    [displayedArtifactMetadata, activeArtifact?.title],
  );
  const metadataSummary = useMemo(
    () => extractMetadataValue(displayedArtifactMetadata, ["summary", "description", "subtitle", "overview"]),
    [displayedArtifactMetadata],
  );
  const metadataSection = useMemo(
    () => extractMetadataValue(displayedArtifactMetadata, ["section", "section_title", "category"]),
    [displayedArtifactMetadata],
  );
  const personaTitle = useMemo(() => normalizeTitleValue(personaLabel), [personaLabel]);
  const latestPrompt = useMemo(() => latestUserMessage(conversationMessages), [conversationMessages]);

  const displayTitle = useMemo(() => {
    const candidate = chooseTitleCandidate(
      [
        metadataTitle,
        fallbackContentTitle,
        metadataSummary,
        fallbackIntentTitle,
        metadataSection,
        fallbackFilenameTitle,
        personaTitle ? `${personaTitle} Artifact` : null,
        "Generated artifact",
      ],
      { prompt: latestPrompt },
    );
    return candidate ?? "Generated artifact";
  }, [
    metadataTitle,
    fallbackContentTitle,
    metadataSummary,
    fallbackIntentTitle,
    metadataSection,
    fallbackFilenameTitle,
    personaTitle,
    latestPrompt,
  ]);
  const versionLabel = activeArtifact?.version ? `v${activeArtifact.version}` : null;
  const displayBadge =
    activeArtifact?.type?.toUpperCase() ||
    activeArtifact?.language?.toUpperCase() ||
    (typeof selectedPreviewMeta?.type === "string" ? selectedPreviewMeta.type.toUpperCase() : undefined) ||
    (typeof selectedPreviewMeta?.language === "string"
      ? (selectedPreviewMeta.language as string).toUpperCase()
      : undefined) ||
    null;
  const displayExtension =
    selectedPreview?.filename?.split(".").pop()?.toUpperCase() ||
    activeArtifact?.filename?.split(".").pop()?.toUpperCase() ||
    null;

  const artifactOptions = useMemo(
    () =>
      displayArtifacts.map((artifact) => ({
        id: artifact.filename,
        label: artifact.title || artifact.filename,
        subtitle: artifact.version ? `v${artifact.version}` : undefined,
      })),
    [displayArtifacts],
  );
  const hasLiveDraft = useMemo(() => liveDraftPreview.trim().length > 0, [liveDraftPreview]);
  const latestProgress = useMemo(
    () => (progressUpdates.length ? progressUpdates[progressUpdates.length - 1] : null),
    [progressUpdates],
  );
  const stageTimeline = useMemo(
    () => buildStageTimeline(progressUpdates, latestProgress?.stage ?? null),
    [progressUpdates, latestProgress?.stage],
  );
  const latestProgressStage = useMemo(() => formatProgressStage(latestProgress?.stage), [latestProgress]);
  const latestProgressPercent = useMemo(() => {
    if (!latestProgress?.progress && latestProgress?.progress !== 0) return null;
    return convertProgressToPercent(latestProgress.progress);
  }, [latestProgress]);

  const liveAnnouncement = useMemo(() => {
    if (streamError) return streamError;
    if (latestProgressStage && latestProgressPercent != null) {
      return `${latestProgressStage} (${latestProgressPercent}% complete)`;
    }
    if (latestProgressStage) return latestProgressStage;
    if (actionStatus) return actionStatus;
    return null;
  }, [streamError, latestProgressStage, latestProgressPercent, actionStatus]);

  const progressSummaryLabel = useMemo(() => {
    if (latestProgressStage) return latestProgressStage;
    if (!latestProgress) return "In progress";
    if (latestProgress.kind === "success") return "Ready";
    if (latestProgress.kind === "error") return "Needs attention";
    return "In progress";
  }, [latestProgress, latestProgressStage]);
  const testCommandLabel = useMemo(() => {
    if (testRunResult?.command) return testRunResult.command;
    if (testArtifactPath) return `pytest ${testArtifactPath}`;
    return null;
  }, [testRunResult?.command, testArtifactPath]);
  const latestTestSummary = useMemo(() => buildTestCommandSummary(testRunResult), [testRunResult]);
  const hasStdout = useMemo(() => Boolean(testRunResult?.stdout && testRunResult.stdout.trim()), [testRunResult?.stdout]);
  const hasStderr = useMemo(() => Boolean(testRunResult?.stderr && testRunResult.stderr.trim()), [testRunResult?.stderr]);
  const activeTestOutput = useMemo(() => {
    if (!testOutputVisible) return "";
    if (!testRunResult) return testRunning ? "Tests in progress…" : "";
    if (testOutputTab === "stderr") return normalizeTestOutput(testRunResult.stderr);
    return normalizeTestOutput(testRunResult.stdout);
  }, [testOutputVisible, testRunResult, testOutputTab, testRunning]);
  const testResultTitle = useMemo(() => {
    if (!testRunResult) return null;
    switch (testRunResult.status) {
      case "passed":
        return "Inline tests passed";
      case "failed":
        return "Inline tests failed";
      case "timeout":
        return "Inline tests timed out";
      default:
        return "Inline tests completed";
    }
  }, [testRunResult]);
  const testResultTimestamp = useMemo(
    () => formatTimeFromIso(testRunResult?.completed_at ?? testRunResult?.started_at),
    [testRunResult?.completed_at, testRunResult?.started_at],
  );

  useEffect(() => {
    if (!actionStatus) return;
    const timeout = window.setTimeout(() => setActionStatus(null), 3200);
    return () => window.clearTimeout(timeout);
  }, [actionStatus]);

  useEffect(() => {
    if (hasRenderContent || hasSourceContent) {
      setLiveDraftPreview("");
    }
  }, [hasRenderContent, hasSourceContent]);

  const downloadArtifact = useCallback(
    async (filename?: string | null) => {
      if (!session?.session_id || !filename) {
        setActionStatus("Select an artifact to download.");
        return;
      }
      try {
        const blob = await downloadAcceleratorBundle(session.session_id, filename);
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
        setActionStatus("Download started.");
      } catch (err) {
        console.error("download_artifact_failed", err);
        setActionStatus("Unable to download artifact.");
      }
    },
    [session?.session_id],
  );

  const handleCopyPreview = useCallback(async () => {
    const textToCopy = previewMode === "source" ? sourceText : previewHtml;
    if (!textToCopy.trim()) {
      setActionStatus("Nothing to copy yet.");
      return;
    }
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(textToCopy);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = textToCopy;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      setActionStatus("Copied preview to clipboard.");
    } catch (err) {
      console.error("copy_preview_failed", err);
      setActionStatus("Unable to copy preview.");
    }
  }, [previewMode, previewHtml, sourceText]);

  const handleDownloadPreview = useCallback(() => {
    void downloadArtifact(selectedArtifactId);
  }, [downloadArtifact, selectedArtifactId]);

  const handleBeginEdit = useCallback(() => {
    const nextDraft = previewMode === "source" ? sourceText : previewHtml;
    setEditDraft(nextDraft);
    const meta = selectedPreview?.meta ?? {};
    setEditSummary(typeof meta.summary === "string" ? meta.summary : "");
    setEditSection(typeof meta.section === "string" ? meta.section : "");
    setEditChangeDescription(typeof meta.change_description === "string" ? meta.change_description : "");
    setEditError(null);
    setEditMode(true);
    setAutoSaveStatus("idle");
    setAutoSaveError(null);
    setAutoSavedAt(null);
    setEditLogPosted(false);
    editMessageRef.current = latestAssistantMessageId || undefined;
    lastSavedPayloadRef.current = {
      content: nextDraft,
      summary: typeof meta.summary === "string" && meta.summary ? meta.summary : undefined,
      section: typeof meta.section === "string" && meta.section ? meta.section : undefined,
      change_description:
        typeof meta.change_description === "string" && meta.change_description ? meta.change_description : undefined,
      message_id: editMessageRef.current,
    };
    trackEvent("accelerator_artifact_edit_start", {
      sessionId: session?.session_id,
      artifact: selectedArtifactId,
    });
  }, [previewMode, previewHtml, sourceText, selectedPreview?.meta, selectedArtifactId, session?.session_id, latestAssistantMessageId]);

  const handleCancelEdit = useCallback(() => {
    setEditMode(false);
    setSavingEdit(false);
    setEditError(null);
    setAutoSaveStatus("idle");
    setAutoSaveError(null);
    setAutoSavedAt(null);
    setEditLogPosted(false);
    if (autoSaveTimerRef.current) {
      window.clearTimeout(autoSaveTimerRef.current);
      autoSaveTimerRef.current = null;
    }
  }, []);

  const appendLocalMessage = useCallback((message: ConversationMessage) => {
    setLocalMessages((prev) => [...prev, message]);
  }, []);

  const logInlineEditRationale = useCallback(
    async (
      payload: AcceleratorArtifactEditRequest,
      responseMeta: Record<string, any> | undefined,
    ) => {
      if (!session) return;
      const rationalePieces: string[] = [];
      if (payload.summary) {
        rationalePieces.push(`- **Summary:** ${payload.summary}`);
      }
      if (payload.section) {
        rationalePieces.push(`- **Section:** ${payload.section}`);
      }
      if (payload.change_description) {
        rationalePieces.push(`- **Change:** ${payload.change_description}`);
      }
      if (!rationalePieces.length) return;

      const messageId = generateClientMessageId("inline-edit");
      const content = `🛠️ Got your inline changes for **${selectedArtifactId}**. I will use this updated version in future drafts:
${rationalePieces.join("\n")}`;

      const localMessage: ConversationMessage = {
        message_id: messageId,
        session_id: session.session_id,
        role: "system",
        content,
        created_at: new Date().toISOString(),
        local: true,
        origin: "inline-edit",
      };
      appendLocalMessage(localMessage);

      try {
        const serverMessage = await postAcceleratorMessage(session.session_id, content, []);
        setLocalMessages((prev) =>
          prev.filter((message) => message.message_id !== messageId || message.origin !== "inline-edit"),
        );
        setData((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            messages: [...prev.messages, serverMessage],
          };
        });
      } catch (err) {
        console.error("inline_edit_rationale_failed", err);
        pushProgressUpdate("Could not log inline edit rationale to conversation.", "error");
      }
    },
    [appendLocalMessage, postAcceleratorMessage, session, selectedArtifactId, pushProgressUpdate, setData],
  );

  const payloadsEqual = useCallback((a: AcceleratorArtifactEditRequest | null, b: AcceleratorArtifactEditRequest | null) => {
    if (a === b) return true;
    if (!a || !b) return false;
    return (
      a.content === b.content &&
      (a.summary || "") === (b.summary || "") &&
      (a.section || "") === (b.section || "") &&
      (a.change_description || "") === (b.change_description || "")
    );
  }, []);

  const buildEditPayload = useCallback((): AcceleratorArtifactEditRequest | null => {
    const trimmedContent = editDraft.trim();
    if (!trimmedContent) return null;
    return {
      content: trimmedContent,
      summary: editSummary.trim() || undefined,
      section: editSection.trim() || undefined,
      change_description: editChangeDescription.trim() || undefined,
      message_id: editMessageRef.current || latestAssistantMessageId || undefined,
    };
  }, [editDraft, editSummary, editSection, editChangeDescription, latestAssistantMessageId]);

  const updateArtifactsFromResponse = useCallback(
    (response: AcceleratorArtifactEditResponse) => {
      if (!selectedArtifactId) return;
      const artifactId = selectedArtifactId;
      setPreviewSource(response.content);
      setPreviewHtml(response.content);
      setPreviewMap((prev) => ({
        ...prev,
        [artifactId]: {
          ...(prev[artifactId] ?? {
            filename: artifactId,
            created_at: response.meta?.edited_at ?? new Date().toISOString(),
          }),
          version: response.version,
          meta: response.meta,
          content: response.content,
        },
      }));
      setLiveArtifacts((prev) => {
        if (!artifactId) return prev;
        const normalized = normalizeArtifacts(prev);
        const replaced = normalized.map((artifact) =>
          artifact.filename === artifactId
            ? {
                ...artifact,
                version: response.version,
                summary: response.meta?.summary ?? artifact.summary,
                meta: response.meta,
                diffSummary: typeof response.meta?.diff_summary === "string" ? response.meta.diff_summary : artifact.diffSummary,
                messageId: typeof response.meta?.message_id === "string" ? response.meta.message_id : artifact.messageId,
                stage: typeof response.meta?.stage === "string" ? response.meta.stage : artifact.stage,
                source: "edit",
              }
            : artifact,
        );
        if (!replaced.some((artifact) => artifact.filename === artifactId)) {
          replaced.push({
            filename: artifactId,
            version: response.version,
            summary: response.meta?.summary,
            meta: response.meta,
            diffSummary: typeof response.meta?.diff_summary === "string" ? response.meta.diff_summary : null,
            messageId: typeof response.meta?.message_id === "string" ? response.meta.message_id : null,
            stage: typeof response.meta?.stage === "string" ? response.meta.stage : null,
            source: "edit",
            created_at: response.meta?.edited_at,
          });
        }
        return replaced;
      });
    },
    [normalizeArtifacts, selectedArtifactId],
  );

  const performAutoSave = useCallback(
    async (payload: AcceleratorArtifactEditRequest) => {
      if (!session?.session_id || !selectedArtifactId) return;
      setAutoSaveStatus("saving");
      setAutoSaveError(null);
      try {
        const response = await patchAcceleratorArtifact(session.session_id, selectedArtifactId, payload);
        lastSavedPayloadRef.current = {
          ...payload,
          content: response.content,
        };
        updateArtifactsFromResponse(response);
        setAutoSaveStatus("saved");
        setAutoSavedAt(Date.now());
        if (!editLogPosted) {
          void logInlineEditRationale(payload, response.meta);
          setEditLogPosted(true);
        }
        window.setTimeout(() => setAutoSaveStatus("idle"), 2500);
      } catch (err: any) {
        const detail = err?.message || "Auto-save failed.";
        setAutoSaveStatus("error");
        setAutoSaveError(detail);
      }
    },
    [session?.session_id, selectedArtifactId, logInlineEditRationale, updateArtifactsFromResponse, editLogPosted],
  );

  useEffect(() => {
    if (!editMode || savingEdit) {
      if (autoSaveTimerRef.current) {
        window.clearTimeout(autoSaveTimerRef.current);
        autoSaveTimerRef.current = null;
      }
      return undefined;
    }
    const payload = buildEditPayload();
    if (!payload) {
      if (autoSaveTimerRef.current) {
        window.clearTimeout(autoSaveTimerRef.current);
        autoSaveTimerRef.current = null;
      }
      return undefined;
    }
    if (payloadsEqual(payload, lastSavedPayloadRef.current)) {
      if (autoSaveTimerRef.current) {
        window.clearTimeout(autoSaveTimerRef.current);
        autoSaveTimerRef.current = null;
      }
      return undefined;
    }
    if (autoSaveTimerRef.current) {
      window.clearTimeout(autoSaveTimerRef.current);
      autoSaveTimerRef.current = null;
    }
    autoSaveTimerRef.current = window.setTimeout(() => {
      performAutoSave(payload);
      autoSaveTimerRef.current = null;
    }, 1500);
    return () => {
      if (autoSaveTimerRef.current) {
        window.clearTimeout(autoSaveTimerRef.current);
        autoSaveTimerRef.current = null;
      }
    };
  }, [buildEditPayload, editMode, savingEdit, performAutoSave, payloadsEqual]);

  useEffect(() => {
    return () => {
      if (autoSaveTimerRef.current) {
        window.clearTimeout(autoSaveTimerRef.current);
        autoSaveTimerRef.current = null;
      }
    };
  }, []);

  const handleSaveEdit = useCallback(async () => {
    if (!session?.session_id || !selectedArtifactId) return;
    const payload = buildEditPayload();
    if (!payload) {
      setEditError("Content cannot be empty.");
      return;
    }
    if (payloadsEqual(payload, lastSavedPayloadRef.current)) {
      setEditMode(false);
      setSavingEdit(false);
      setEditError(null);
      setAutoSaveStatus("idle");
      setAutoSaveError(null);
      setAutoSavedAt(Date.now());
      return;
    }
    try {
      setSavingEdit(true);
      setEditError(null);
      const response = await patchAcceleratorArtifact(session.session_id, selectedArtifactId, payload);
      updateArtifactsFromResponse(response);
      lastSavedPayloadRef.current = {
        ...payload,
        content: response.content,
      };
      trackEvent("accelerator_artifact_edit_saved", {
        sessionId: session.session_id,
        artifact: selectedArtifactId,
      });
      setEditMode(false);
      setSavingEdit(false);
      setAutoSaveStatus("saved");
      setAutoSavedAt(Date.now());
      pushProgressUpdate("Artifact updated with your inline edit and linked back to this conversation.", "success");
      void logInlineEditRationale(payload, response.meta);
      setEditLogPosted(true);
    } catch (err: any) {
      const detail = err?.message || "Unable to save edits.";
      setEditError(detail);
      setSavingEdit(false);
    }
  }, [
    session?.session_id,
    selectedArtifactId,
    buildEditPayload,
    payloadsEqual,
    updateArtifactsFromResponse,
    pushProgressUpdate,
    logInlineEditRationale,
    trackEvent,
  ]);

  const activeSwitcherLabel = useMemo(() => {
    if (!selectedArtifactId) return "Artifacts";
    const current = artifactDetails.get(selectedArtifactId);
    return current?.title || current?.filename || selectedArtifactId;
  }, [artifactDetails, selectedArtifactId]);

  const showPreviewPanel = Boolean(hasRenderContent || hasSourceContent || selectedPreview);

  const previewMenuEnabled = useMemo(
    () =>
      Boolean(
        selectedArtifactId ||
        (previewMode === "source" ? sourceText : previewHtml).trim(),
      ),
    [selectedArtifactId, previewMode, sourceText, previewHtml],
  );

  const canCopyPreview = useMemo(
    () => Boolean((previewMode === "source" ? sourceText : previewHtml).trim()),
    [previewMode, sourceText, previewHtml],
  );

  useEffect(() => {
    if (!previewMenuEnabled) {
      setPreviewActionsOpen(false);
    }
  }, [previewMenuEnabled]);

  const refreshSession = useCallback(
    async (id: string, options?: { refreshPreviews?: boolean }) => {
      try {
        const fresh = await getAcceleratorSession(id);
        setData(fresh);
        setPromotionProjectId(fresh.session.project_id ?? null);
        if (options?.refreshPreviews) {
          const cancelledRef = { current: false };
          void refreshPreviews({ cancelledRef });
        }
      } catch (e: any) {
        setError(e?.message || "Unable to refresh session.");
      }
    },
    [refreshPreviews],
  );

  const handleSend = useCallback(
    async (event?: FormEvent, override?: string) => {
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
      setAllowProgress(true);
      setActionStatus("Preparing your draft…");
      pushProgressUpdate("Preparing your draft…", "info", "analysis", 5);
      const pendingId = `pending-${Date.now()}`;
      const optimisticMessage: ConversationMessage = {
        message_id: pendingId,
        session_id: session.session_id,
        role: "user",
        content: messageToSend,
        created_at: new Date().toISOString(),
        pending: true,
      };
      setPendingMessages((prev) => [...prev, optimisticMessage]);

      try {
        const providerOverride = selectedModelOption?.available ? selectedModelOption.provider : null;
        const modelOverride = selectedModelOption?.available ? selectedModelOption.model : null;
        trackEvent("accelerator_prompt_sent", {
          sessionId: session.session_id,
          intentId: intent?.intent_id,
          length: content.length,
          model: modelOverride,
          provider: providerOverride,
          tone: toneProfile,
          extendedThinking: connectorSettings.extendedThinking,
          research: connectorSettings.research,
          stylistic: connectorSettings.useStyle,
        });
        await postAcceleratorMessage(session.session_id, content, {
          provider: providerOverride,
          model: modelOverride,
        });
        await refreshSession(session.session_id, { refreshPreviews: true });
      } catch (e: any) {
        setError(e?.message || "Unable to send message right now.");
        if (!override) {
          setDraft(messageToSend);
        }
        setPendingMessages((prev) => prev.filter((msg) => msg.message_id !== pendingId));
      } finally {
        setPendingMessages((prev) => prev.filter((msg) => msg.message_id !== pendingId));
        setSending(false);
      }
    },
    [
      session,
      sending,
      draft,
      intent?.intent_id,
      refreshSession,
      selectedModelOption,
      connectorSettings,
      toneProfile,
    ],
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
        {personaLabel && <div className="accelerator-meta" role="list"><span role="listitem">Persona: {personaLabel}</span></div>}
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
      {streamError ? (
        <div className="accelerator-status accelerator-status--warning" role="status">
          <p>{streamError}</p>
          {streamTimeoutReached && (
            <div className="accelerator-status__actions">
              <button type="button" onClick={handleRetryStream} className="btn btn-secondary">
                Retry live builder
              </button>
              {promotionProjectId && (
                <button type="button" onClick={handleOpenWorkspace} className="btn btn-tertiary">
                  Open project workspace
                </button>
              )}
            </div>
          )}
        </div>
      ) : null}

      <main className="accelerator-main">
        {liveAnnouncement ? (
          <div className="sr-only" role="status" aria-live="polite">
            {liveAnnouncement}
          </div>
        ) : null}
        <div className="accelerator-layout">
          <section
            className="accelerator-chat"
            aria-label="Conversation"
            aria-busy={sending || streaming || undefined}
          >
            {loading && !session && <div className="accelerator-status">Loading accelerator…</div>}
            {!loading && session && (
              <>
                <ol className="accelerator-messages">
                {conversationMessages.map((message) => {
                  const isAssistant = message.role === "assistant";
                  const showArtifactsInline =
                    isAssistant &&
                    message.message_id === latestAssistantMessageId &&
                    displayArtifacts.length > 0;
                  const isPending = Boolean(message.pending);

                  const assistantDisplay = intent?.title ?? "Assistant";
                  const assistantInitials = assistantDisplay
                    .split(/\s+/)
                    .map((part) => part[0])
                    .join("")
                    .slice(0, 2)
                    .toUpperCase();

                  let content = message.content;
                  if (warmGuidanceActive && isAssistant) {
                    const prefix =
                      toneProfile === "warm-novice"
                        ? "✨ I'm on your team. Let's walk through this step-by-step:\n\n"
                        : "🌟 Here's what I'm seeing:\n\n";
                    const suffix =
                      toneProfile === "warm-novice"
                        ? "\n\n💡 *Tip:* I'll keep explanations approachable—just say 'Explain more' if you need extra context."
                        : "\n\n🤝 Want alternatives or deeper dives? Just ask and I'll share playbook-style pointers.";
                    content = `${prefix}${message.content.trim()}${suffix}`;
                  }
                  return (
                    <li
                      key={message.message_id}
                      className={`accelerator-message accelerator-message--${message.role} ${
                        isPending ? "accelerator-message--pending" : ""
                      } ${highlightedMessageId === message.message_id ? "accelerator-message--highlight" : ""}`}
                      ref={(node) => {
                        if (!message.message_id) return;
                        const map = messageNodeMapRef.current;
                        if (node) map.set(message.message_id, node);
                        else map.delete(message.message_id);
                      }}
                    >
                      <span className="accelerator-message__role">
                        {isAssistant ? (
                          <>
                            <span aria-hidden="true" className="accelerator-message__avatar">
                              {assistantInitials}
                            </span>
                            {assistantDisplay}
                          </>
                        ) : (
                          "You"
                        )}
                      </span>
                      <div className="accelerator-message__bubble">
                        <MarkdownMessage>{content}</MarkdownMessage>
                      </div>
                      {showArtifactsInline ? (
                        <div className="accelerator-inline-artifact-card" aria-label="Generated artifacts">
                          <header className="accelerator-inline-artifact-card__header">
                            <span className="accelerator-inline-artifact-card__label">Generated artifacts</span>
                            <span className="accelerator-inline-artifact-card__count" aria-live="polite">
                              {displayArtifacts.length} files
                            </span>
                          </header>
                          <p className="accelerator-inline-artifact-card__hint">
                            View and manage these files in the workspace panel on the right.
                          </p>
                        </div>
                      ) : null}
                    </li>
                  );
                })}
                {(() => {
                  const statusText =
                    actionStatus || latestProgress?.message || (streaming && !streamError ? "Generating artifacts…" : null);
                  if (!statusText) return null;
                  return (
                    <li className="accelerator-message accelerator-message--assistant accelerator-message--status" role="status">
                      <div className="accelerator-message__bubble accelerator-message__bubble--status">{statusText}</div>
                    </li>
                  );
                })()}
                </ol>
                <div ref={messagesEndRef} />
              </>
            )}
            <div className="accelerator-tone-row" aria-live="polite">
              <div className="accelerator-tone-indicator" aria-live="polite">
                <div className="accelerator-tone-indicator__label">
                  Tone: {toneProfile === "warm-novice" ? "Novice-friendly" : toneProfile === "warm-expert" ? "Collaborative expert" : "Concise"}
                  <span className="accelerator-tone-indicator__hint">
                    {TONE_DESCRIPTIONS[toneProfile]}
                  </span>
                </div>
                <div className="accelerator-tone-indicator__tips" aria-live="polite">
                  {TONE_COACHING_TIPS[toneProfile].map((tip) => (
                    <span key={tip} className="accelerator-tone-indicator__tip">
                      {tip}
                    </span>
                  ))}
                </div>
              </div>
              <div className="accelerator-tone-toggle">
                <button
                  type="button"
                  className="accelerator-tone-toggle__trigger"
                  aria-haspopup="true"
                  aria-expanded={showToneMenu}
                  onClick={() => setShowToneMenu((current) => !current)}
                >
                  {TONE_LABELS[toneProfile]}
                </button>
                {showToneMenu ? (
                  <ul className="accelerator-tone-toggle__menu" role="menu">
                    {(Object.keys(TONE_LABELS) as ToneProfile[]).map((toneKey) => (
                      <li key={toneKey} role="menuitem">
                        <button
                          type="button"
                          className={toneKey === toneProfile ? "accelerator-tone-toggle__option accelerator-tone-toggle__option--active" : "accelerator-tone-toggle__option"}
                          onClick={() => {
                            setToneProfile(toneKey);
                            setShowToneMenu(false);
                            trackEvent("accelerator_tone_selected", {
                              sessionId: session?.session_id,
                              tone: toneKey,
                            });
                          }}
                        >
                          <span className="accelerator-tone-toggle__title">{TONE_LABELS[toneKey]}</span>
                          <span className="accelerator-tone-toggle__description">{TONE_DESCRIPTIONS[toneKey]}</span>
                          <span className="accelerator-tone-toggle__coaching">{TONE_COACHING_TIPS[toneKey][0]}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            </div>
            <ChatComposer
              className="accelerator-composer"
              draft={draft}
              onDraftChange={setDraft}
              onSubmit={(event) => handleSend(event)}
              sending={sending}
              textareaDisabled={sending || loading || !session}
              hasSession={Boolean(session)}
              modelOptions={modelOptions}
              modelLoading={modelLoading}
              modelError={modelError}
              selectedModelKey={selectedModelKey}
              onModelChange={(value) => {
                setSelectedModelKey(value);
                const [provider, ...rest] = value.split(":");
                const model = rest.join(":");
                setModelPreference(provider, model);
                trackEvent("accelerator_model_changed", {
                  sessionId: session?.session_id,
                  provider,
                  model,
                });
              }}
              resourceMenu={resourceMenuConfig}
              connectorsMenu={connectorMenuConfig}
              extendedThinking={extendedThinkingConfig}
              placeholder={TONE_PLACEHOLDER_MAP[toneProfile]}
              sendIcon={<span aria-hidden="true">↑</span>}
            />
            {artifactCount > 0 && !drawerOpen ? (
              <button
                type="button"
                className="accelerator-drawer-toggle"
                onClick={() => setDrawerOpen(true)}
                aria-label={`Open artifacts panel (${artifactCount} file${artifactCount === 1 ? "" : "s"})`}
              >
                <span className="accelerator-drawer-toggle__label">View generated artifacts</span>
                <span className="accelerator-drawer-toggle__count" aria-hidden="true">
                  {artifactCount}
                </span>
                <span className="accelerator-drawer-toggle__icon" aria-hidden="true">
                  ▸
                </span>
              </button>
            ) : null}
          </section>
        </div>
      </main>
      <div
        className={`drawer drawer--accelerator${drawerOpen ? " open" : ""}`}
        role={drawerOpen ? "dialog" : undefined}
        aria-modal={drawerOpen ? "true" : undefined}
        aria-hidden={drawerOpen ? undefined : "true"}
        aria-label="Generated artifacts"
      >
        <div
          className="drawer__backdrop"
          onClick={() => {
            setDrawerOpen(false);
            setDrawerExpanded(false);
            setArtifactMenuOpen(false);
            setPreviewActionsOpen(false);
          }}
        />
        <div
          className={`drawer__panel accelerator-drawer__panel${drawerExpanded ? " drawer__panel--wide accelerator-drawer__panel--expanded" : ""}`}
        >
          <div className="accelerator-preview-rail">
            <div className="accelerator-preview-rail__inner">
              <header className="accelerator-drawer__header">
                <div className="accelerator-drawer__title" ref={artifactMenuContainerRef}>
                  <button
                    type="button"
                    className="accelerator-drawer__menu-trigger"
                    aria-haspopup="listbox"
                    aria-expanded={artifactMenuOpen}
                    aria-label={
                      artifactMenuOpen
                        ? "Close artifact menu"
                        : `Show artifact menu (current: ${activeSwitcherLabel})`
                    }
                    onClick={() => setArtifactMenuOpen((open) => !open)}
                  >
                    <span aria-hidden="true">☰</span>
                  </button>
                  <div className="accelerator-drawer__heading">
                    <span className="accelerator-drawer__eyebrow">Generated artifacts</span>
                    <span className="accelerator-drawer__label">{displayTitle}</span>
                  </div>
                  {artifactMenuOpen ? (
                    <div className="accelerator-drawer__menu" role="listbox">
                      <span className="accelerator-drawer__menu-label">Switch between artifacts</span>
                      <ul>
                        {displayArtifacts.map((artifact) => {
                          const active = artifact.filename === selectedArtifactId;
                          return (
                            <li key={artifact.filename}>
                              <button
                                type="button"
                                className={
                                  active
                                    ? "accelerator-drawer__menu-item accelerator-drawer__menu-item--active"
                                    : "accelerator-drawer__menu-item"
                                }
                                onClick={() => {
                                  handleSelectArtifact(artifact.filename);
                                  setArtifactMenuOpen(false);
                                }}
                                role="option"
                                aria-selected={active}
                              >
                                <span className="accelerator-drawer__menu-title">{artifact.title || artifact.filename}</span>
                                {artifact.version ? (
                                  <span className="accelerator-drawer__menu-tag">v{artifact.version}</span>
                                ) : null}
                                {artifact.messageIds?.length ? (
                                  <span className="accelerator-drawer__menu-source">Linked to {artifact.messageIds.length} message{artifact.messageIds.length > 1 ? "s" : ""}</span>
                                ) : null}
                                {artifact.diffSummary ? (
                                  <span className="accelerator-drawer__menu-diff">Updated: {artifact.diffSummary}</span>
                                ) : null}
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ) : null}
                </div>
                <div className="accelerator-drawer__actions">
                  <button
                    type="button"
                    className="accelerator-drawer__expand"
                    onClick={() => setDrawerExpanded((value) => !value)}
                    aria-pressed={drawerExpanded}
                  >
                    {drawerExpanded ? "Collapse" : "Expand"}
                  </button>
                  <button
                    type="button"
                    className="accelerator-drawer__close"
                    onClick={() => {
                      setDrawerOpen(false);
                      setDrawerExpanded(false);
                      setArtifactMenuOpen(false);
                      setPreviewActionsOpen(false);
                    }}
                  >
                    Hide panel
                  </button>
                </div>
              </header>
              {showProgressPanel ? (
                <section className="accelerator-progress" aria-label="Live build status" aria-live="polite">
                  <div className="accelerator-progress__header">
                    <span className="accelerator-progress__eyebrow">Live build</span>
                    <span className="accelerator-progress__summary">{progressSummaryLabel}</span>
                    {latestProgressPercent != null ? (
                      <span className="accelerator-progress__percent" aria-label="Completion percent">
                        {latestProgressPercent}%
                      </span>
                    ) : null}
                    {progressElapsedLabel ? <span className="accelerator-progress__elapsed">{progressElapsedLabel}</span> : null}
                  </div>
                  {(connectionNotice || heartbeatStale || reconnectingStream) && (
                    <div className="accelerator-progress__connection" role="status">
                      <span className="accelerator-progress__connection-dot" aria-hidden="true" />
                      <span>
                        {reconnectingStream
                          ? connectionNotice || "Live builder connection lost. Attempting to reconnect…"
                          : connectionNotice || "Monitoring live builder heartbeat…"}
                      </span>
                    </div>
                  )}
                  {stageTimeline.length > 0 ? (
                    <div className="accelerator-progress__timeline" role="list" aria-label="Stage timeline">
                      {stageTimeline.map((item, index) => (
                        <div
                          key={`${item.stage}-${index}`}
                          className={`accelerator-progress__timeline-step accelerator-progress__timeline-step--${item.state}`}
                          role="listitem"
                        >
                          {index > 0 ? <span className="accelerator-progress__timeline-connector" aria-hidden="true" /> : null}
                          <span className="accelerator-progress__timeline-dot" aria-hidden="true" />
                          <span className="accelerator-progress__timeline-label">{item.label}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {latestProgressPercent != null ? (
                    <div
                      className="accelerator-progress__meter"
                      role="progressbar"
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={latestProgressPercent}
                      aria-label={progressSummaryLabel}
                    >
                      <div className="accelerator-progress__meter-fill" style={{ width: `${latestProgressPercent}%` }} />
                    </div>
                  ) : progressInFlight ? (
                    <div className="accelerator-progress__meter accelerator-progress__meter--indeterminate" aria-hidden="true">
                      <div className="accelerator-progress__spinner" />
                    </div>
                  ) : null}
                  <ol
                    className="accelerator-progress__list"
                    role="status"
                    aria-live="polite"
                    aria-label="Live artifact progress"
                  >
                    {progressUpdates.map((step) => (
                      <li
                        key={step.id}
                        className={`accelerator-progress__item accelerator-progress__item--${step.kind}`}
                      >
                        <span className="accelerator-progress__dot" aria-hidden="true" />
                        <div className="accelerator-progress__body">
                          <span className="accelerator-progress__message">{step.message}</span>
                          <span className="accelerator-progress__meta">
                            {formatProgressStage(step.stage) ? (
                              <span className="accelerator-progress__chip">{formatProgressStage(step.stage)}</span>
                            ) : null}
                            {typeof step.progress === "number" ? (
                              <span className="accelerator-progress__percent accelerator-progress__percent--inline">{step.progress}%</span>
                            ) : null}
                            <span className="accelerator-progress__time">
                              {new Date(step.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                            </span>
                          </span>
                        </div>
                      </li>
                    ))}
                  </ol>
                </section>
              ) : null}
              <div className="accelerator-drawer__content">
                <div className="accelerator-drawer__body" aria-live="polite">
                  {showPreviewPanel ? (
                    <div className="accelerator-preview-card">
                      <header className="accelerator-preview-card__header" ref={previewActionsRef}>
                        <div className="accelerator-preview-card__summary">
                          <span className="accelerator-preview-card__eyebrow">Active artifact</span>
                          <h3 className="accelerator-preview-card__title">{displayTitle}</h3>
                          <div className="accelerator-preview-card__chips">
                            {versionLabel ? (
                              <span className="accelerator-preview-card__chip accelerator-preview-card__chip--artifact" aria-label={`Artifact version ${versionLabel}`}>
                                {versionLabel}
                              </span>
                            ) : null}
                            {activeArtifactCreatedAt ? (
                              <span className="accelerator-preview-card__chip accelerator-preview-card__chip--artifact" aria-label={`Updated ${activeArtifactCreatedAt}`}>
                                Updated {activeArtifactCreatedAt}
                              </span>
                            ) : null}
                            {activeArtifact?.stage ? (
                              <span className="accelerator-preview-card__chip accelerator-preview-card__chip--artifact" aria-label={`Generation stage ${activeArtifact.stage}`}>
                                {formatBadgeLabel(activeArtifact.stage)}
                              </span>
                            ) : null}
                          </div>
                          {activeArtifactMessages.length > 0 ? (
                            <div className="accelerator-preview-card__meta-group" role="group" aria-label="Linked conversation messages">
                              {activeArtifactMessages.map((linked) => (
                                <span key={linked.id} className={chipClassForRole(linked.role)}>
                                  <button type="button" onClick={() => handleJumpToMessage(linked.id)}>
                                    {formatBadgeLabel(linked.role) ?? "Message"} • {linked.label}
                                  </button>
                                </span>
                              ))}
                            </div>
                          ) : null}
                        </div>
                        <div className="accelerator-preview-card__toolbar">
                          <div className="accelerator-preview-card__view-toggle" role="group" aria-label="Preview mode">
                            <button
                              type="button"
                              className={
                                previewMode === "render"
                                  ? "accelerator-preview-toggle accelerator-preview-toggle--active"
                                  : "accelerator-preview-toggle"
                              }
                              onClick={() => {
                                setPreviewMode("render");
                                setPreviewActionsOpen(false);
                              }}
                              disabled={!hasRenderContent}
                              aria-pressed={previewMode === "render"}
                            >
                              <span className="accelerator-preview-toggle__icon" aria-hidden="true">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                                  <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7Z" />
                                  <circle cx="12" cy="12" r="3.5" />
                                </svg>
                              </span>
                              <span>Preview</span>
                            </button>
                            <button
                              type="button"
                              className={
                                previewMode === "source"
                                  ? "accelerator-preview-toggle accelerator-preview-toggle--active"
                                  : "accelerator-preview-toggle"
                              }
                              onClick={() => {
                                setPreviewMode("source");
                                setPreviewActionsOpen(false);
                              }}
                              disabled={!hasSourceContent && !previewHtml.trim()}
                              aria-pressed={previewMode === "source"}
                            >
                              <span className="accelerator-preview-toggle__icon" aria-hidden="true">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                                  <polyline points="16 18 22 12 16 6" />
                                  <polyline points="8 6 2 12 8 18" />
                                </svg>
                              </span>
                              <span>Source</span>
                            </button>
                          </div>
                          <div className="accelerator-preview-card__menu">
                            <button
                              type="button"
                              className="accelerator-preview-card__menu-trigger"
                              onClick={() => {
                                if (!previewMenuEnabled) return;
                                setPreviewActionsOpen((open) => !open);
                              }}
                              aria-haspopup="true"
                              aria-expanded={previewActionsOpen}
                              disabled={!previewMenuEnabled}
                              aria-label="Artifact actions"
                            >
                              <span aria-hidden="true">⋮</span>
                            </button>
                            {previewActionsOpen ? (
                              <div className="accelerator-preview-card__menu-popover" role="menu">
                                <button
                                  type="button"
                                  role="menuitem"
                                  onClick={() => {
                                    handleCopyPreview();
                                    setPreviewActionsOpen(false);
                                  }}
                                  disabled={!canCopyPreview}
                                >
                                  Copy to clipboard
                                </button>
                                <button
                                  type="button"
                                  role="menuitem"
                                  onClick={() => {
                                    if (editMode) {
                                      handleCancelEdit();
                                    } else {
                                      handleBeginEdit();
                                    }
                                    setPreviewActionsOpen(false);
                                  }}
                                  disabled={!selectedArtifactId || savingEdit}
                                >
                                  {editMode ? "Exit inline editor" : "Start inline edit"}
                                </button>
                                <button
                                  type="button"
                                  role="menuitem"
                                  onClick={() => {
                                    handleDownloadPreview();
                                    setPreviewActionsOpen(false);
                                  }}
                                  disabled={!selectedArtifactId}
                                >
                                  Download file
                                </button>
                              </div>
                            ) : null}
                          </div>
                        </div>
                      </header>
                  {actionStatus ? <div className="accelerator-preview-card__status">{actionStatus}</div> : null}
                  <div className="accelerator-preview-card__body">
                    {activeArtifactDiffSegments.length > 0 ? (
                      <section className="accelerator-preview-card__diff" aria-label="Change summary">
                        <h4>Change highlights</h4>
                        <ul className="accelerator-preview-card__diff-list">
                          {activeArtifactDiffSegments.map((segment) => (
                            <li
                              key={segment.id}
                              className={`accelerator-preview-card__diff-item accelerator-preview-card__diff-item--${segment.kind}`}
                            >
                              {segment.kind === "added" ? "+" : segment.kind === "removed" ? "−" : "•"} {segment.text}
                            </li>
                          ))}
                        </ul>
                      </section>
                    ) : diffSummary ? (
                      <div className="accelerator-preview-card__status accelerator-preview-card__status--diff" aria-label="Change summary">
                        {diffSummary}
                      </div>
                    ) : null}
                    {editMode ? (
                      <div className="accelerator-preview-card__edit">
                        <label className="accelerator-preview-card__edit-label" htmlFor="artifact-editor">
                          Artifact content
                        </label>
                        <textarea
                          id="artifact-editor"
                          className="accelerator-preview-card__edit-textarea"
                          value={editDraft}
                          onChange={(event) => setEditDraft(event.target.value)}
                          rows={18}
                        />
                        <div className="accelerator-preview-card__edit-grid">
                          <label className="accelerator-preview-card__edit-field">
                            <span>Summary</span>
                            <input
                              type="text"
                              value={editSummary}
                              onChange={(event) => setEditSummary(event.target.value)}
                              placeholder="Short blurb shown in artifact list"
                            />
                          </label>
                          <label className="accelerator-preview-card__edit-field">
                            <span>Section</span>
                            <input
                              type="text"
                              value={editSection}
                              onChange={(event) => setEditSection(event.target.value)}
                              placeholder="Which section was updated?"
                            />
                          </label>
                          <label className="accelerator-preview-card__edit-field accelerator-preview-card__edit-field--full">
                            <span>Change description</span>
                            <input
                              type="text"
                              value={editChangeDescription}
                              onChange={(event) => setEditChangeDescription(event.target.value)}
                              placeholder="Optional context for collaborators"
                            />
                          </label>
                        </div>
                        {editError ? (
                          <div className="accelerator-status accelerator-status--error" role="alert">
                            {editError}
                          </div>
                        ) : null}
                        <div className="accelerator-preview-card__edit-actions">
                          <button
                            type="button"
                            className="btn btn-primary"
                            onClick={handleSaveEdit}
                            disabled={savingEdit}
                          >
                            {savingEdit ? "Saving…" : "Save changes"}
                          </button>
                          <button type="button" className="btn btn-secondary" onClick={handleCancelEdit} disabled={savingEdit}>
                            Cancel
                          </button>
                        </div>
                        <div className="accelerator-preview-card__autosave" role="status" aria-live="polite">
                          {autoSaveStatus === "saving" && "Auto-saving changes…"}
                          {autoSaveStatus === "error" && autoSaveError}
                          {autoSaveStatus === "saved" && autoSavedAt
                            ? `Last saved at ${new Date(autoSavedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`
                            : null}
                        </div>
                      </div>
                    ) : previewMode === "render" ? (
                      selectedIsHtml ? (
                        renderContent.trim() || htmlIframeUrl ? (
                          <div
                            className="accelerator-preview-card__frame"
                            style={frameHeight ? { minHeight: frameHeight, height: frameHeight } : undefined}
                          >
                            <iframe
                              ref={previewIframeRef}
                              {...(htmlIframeUrl ? { src: htmlIframeUrl } : { srcDoc: renderContent })}
                              title={
                                activeArtifact?.title ||
                                activeArtifact?.filename ||
                                selectedPreview?.filename ||
                                "Live preview"
                              }
                              loading="lazy"
                              allow="clipboard-write"
                              sandbox="allow-scripts allow-same-origin allow-popups allow-top-navigation-by-user-activation"
                              aria-label="Live document preview"
                            />
                          </div>
                        ) : (
                          <div className="accelerator-preview-card__empty">Preview not available for this artifact.</div>
                        )
                      ) : (
                        <div className="accelerator-preview-card__markdown" role="article" aria-label="Rendered artifact">
                          <MarkdownMessage className="accelerator-preview-card__content">
                            {renderContent || ""}
                          </MarkdownMessage>
                        </div>
                      )
                    ) : sourceText.trim() ? (
                      <pre className="accelerator-preview-card__source" aria-label="Source code" tabIndex={0}>
                        <code>{sourceText}</code>
                      </pre>
                    ) : (
                      <div className="accelerator-preview-card__empty">
                        Source view is unavailable for this artifact.
                      </div>
                    )}

                    {canRunTests ? (
                      <section className="accelerator-test-runner" aria-label="Inline test runner" aria-live="polite">
                        <div className="accelerator-test-runner__header">
                          <div className="accelerator-test-runner__titles">
                            <span className="accelerator-test-runner__eyebrow">Quality check</span>
                            <h4 className="accelerator-test-runner__title">Inline test runner</h4>
                            {testCommandLabel ? (
                              <code className="accelerator-test-runner__command" aria-label="Test command">
                                {testCommandLabel}
                              </code>
                            ) : null}
                          </div>
                          <div className="accelerator-test-runner__actions">
                            <button
                              type="button"
                              className="accelerator-test-runner__button"
                              onClick={handleRunTests}
                              disabled={testRunning || !canRunTests}
                            >
                              {testRunning ? "Running tests…" : "Run tests"}
                            </button>
                            {testRunResult ? (
                              <button
                                type="button"
                                className="accelerator-test-runner__button accelerator-test-runner__button--ghost"
                                onClick={() => setTestOutputVisible((value) => !value)}
                              >
                                {testOutputVisible ? "Hide output" : "Show output"}
                              </button>
                            ) : null}
                          </div>
                        </div>

                        {testRunning && !testRunResult ? (
                          <div className="accelerator-test-runner__status" role="status">
                            <span className="accelerator-test-runner__spinner" aria-hidden="true" />
                            Running tests against autogenerated assets…
                          </div>
                        ) : null}

                        {testRunError ? (
                          <ResultBanner tone="danger" title="Test execution failed" subtitle={testResultTimestamp ?? undefined}>
                            <p>{testRunError}</p>
                          </ResultBanner>
                        ) : null}

                        {testRunResult ? (
                          <ResultBanner
                            tone={testStatusToTone(testRunResult.status)}
                            title={testResultTitle ?? "Inline test run"}
                            subtitle={testResultTimestamp ?? undefined}
                            action={
                              testRunResult.command ? (
                                <code className="accelerator-test-runner__chip">{testRunResult.command}</code>
                              ) : undefined
                            }
                          >
                            <p>{latestTestSummary}</p>
                          </ResultBanner>
                        ) : null}

                        {testRunResult && testOutputVisible ? (
                          <div className="accelerator-test-runner__output">
                            {hasStdout && hasStderr ? (
                              <div className="accelerator-test-runner__tabs" role="tablist">
                                <button
                                  type="button"
                                  role="tab"
                                  aria-selected={testOutputTab === "stdout"}
                                  className={
                                    testOutputTab === "stdout"
                                      ? "accelerator-test-runner__tab accelerator-test-runner__tab--active"
                                      : "accelerator-test-runner__tab"
                                  }
                                  onClick={() => setTestOutputTab("stdout")}
                                >
                                  Stdout
                                </button>
                                <button
                                  type="button"
                                  role="tab"
                                  aria-selected={testOutputTab === "stderr"}
                                  className={
                                    testOutputTab === "stderr"
                                      ? "accelerator-test-runner__tab accelerator-test-runner__tab--active"
                                      : "accelerator-test-runner__tab"
                                  }
                                  onClick={() => setTestOutputTab("stderr")}
                                >
                                  Stderr
                                </button>
                              </div>
                            ) : null}

                            <pre className="accelerator-test-runner__log" aria-label={testOutputTab === "stderr" ? "Standard error log" : "Standard output log"}>
                              <code>{activeTestOutput || "No output captured."}</code>
                            </pre>
                          </div>
                        ) : null}
                      </section>
                    ) : null}
                  </div>
                </div>
              ) : hasLiveDraft ? (
                <div className="accelerator-preview-card">
                  <header className="accelerator-preview-card__header">
                    <div className="accelerator-preview-card__header-left">
                      <span className="accelerator-drawer__eyebrow">Draft in progress</span>
                      <span className="accelerator-drawer__label">We’re assembling your document live.</span>
                    </div>
                    {activeArtifactMessages.length > 0 ? (
                      <div className="accelerator-preview-card__meta-group" role="group" aria-label="Linked conversation messages">
                        {activeArtifactMessages.map((linked) => (
                          <span key={linked.id} className={chipClassForRole(linked.role)}>
                            <button type="button" onClick={() => handleJumpToMessage(linked.id)}>
                              {formatBadgeLabel(linked.role) ?? "Message"} • {linked.label}
                            </button>
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </header>
                  <div className="accelerator-preview-card__body">
                    <div className="accelerator-preview-card__markdown">
                      <MarkdownMessage className="accelerator-preview-card__content">
                        {liveDraftPreview}
                      </MarkdownMessage>
                    </div>
                    <div className="accelerator-preview-card__status">
                      Updates stream here while the final artifact is prepared. We’ll highlight the exact chat turn that influenced this draft and you can ask for tweaks anytime.
                    </div>
                  </div>
                </div>
              ) : (
                <div className="accelerator-preview-card accelerator-preview-card--empty">
                  Select an artifact to preview the final experience.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
);
}
