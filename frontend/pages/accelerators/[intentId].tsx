import Link from "next/link";
import { useRouter } from "next/router";
import type { FormEvent } from "react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
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
  type AcceleratorPreview,
  type ChatModelOption,
  downloadAcceleratorBundle,
} from "../../lib/api";
import { useUserContext } from "../../lib/user-context";
import { getModelPreference, setModelPreference } from "../../lib/modelPreference";
import ChatComposer, {
  type ChatComposerConnectorToggle,
  type ChatComposerResourceMenuItem,
} from "../../components/chat/ChatComposer";
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

type SimplifiedArtifact = {
  filename: string;
  created_at?: string;
  version?: number;
  summary?: string;
  title?: string;
  type?: string;
  language?: string;
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
  const [streamError, setStreamError] = useState<string | null>(null);
  const heartbeatTimeoutMs = 15000;

  useEffect(() => {
    if (!heartbeatAt) return;
    const timer = window.setTimeout(() => {
      if (heartbeatAt && Date.now() - heartbeatAt > heartbeatTimeoutMs) {
        setStreamError("Waiting for new artifacts. Generation is still in progress...");
      }
    }, heartbeatTimeoutMs);
    return () => window.clearTimeout(timer);
  }, [heartbeatAt]);

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
  const messages = useMemo(() => data?.messages ?? [], [data?.messages]);
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
    return list.map((item) => {
      const meta = item?.meta ?? {};
      const versionValue = meta?.version;
      let parsedVersion: number | undefined;
      if (typeof versionValue === "number") parsedVersion = versionValue;
      else if (typeof versionValue === "string") {
        const numeric = Number(versionValue);
        parsedVersion = Number.isFinite(numeric) ? numeric : undefined;
      }

      return {
        filename: String(item?.filename ?? ""),
        created_at: typeof item?.created_at === "string" ? item.created_at : undefined,
        version: parsedVersion,
        summary: typeof meta?.summary === "string" ? meta.summary : undefined,
        title: typeof meta?.title === "string" ? meta.title : undefined,
        type: typeof meta?.type === "string" ? meta.type : undefined,
        language: typeof meta?.language === "string" ? meta.language : undefined,
      } satisfies SimplifiedArtifact;
    });
  }, []);

  const artifacts = useMemo(() => {
    const meta = session?.metadata;
    const list = (meta as any)?.artifacts;
    return normalizeArtifacts(list);
  }, [session?.metadata, normalizeArtifacts]);

  const displayArtifacts = liveArtifacts.length ? liveArtifacts : artifacts;
  const artifactCount = displayArtifacts.length;

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
    void listAcceleratorPreviews(session.session_id)
      .then((list: AcceleratorPreview[]) => {
        if (cancelled) return;
        setPreviewMap((prev) => {
          const next = { ...prev };
          list.forEach((item) => {
            next[item.filename] = item;
          });
          return next;
        });
      })
      .catch((err: unknown) => console.error("list_previews_failed", err));
    return () => {
      cancelled = true;
    };
  }, [session?.session_id]);

  const artifactDetails = useMemo(() => {
    const map = new Map<string, SimplifiedArtifact>();
    for (const item of displayArtifacts) {
      if (!item.filename) continue;
      map.set(item.filename, item);
    }
    return map;
  }, [displayArtifacts]);

  useEffect(() => {
    if (artifactCount === 0) {
      setSelectedArtifactId(null);
      setSelectedPreview(null);
      setPreviewHtml("");
      setPreviewSource("");
      return;
    }
    if (!selectedArtifactId || !artifactDetails.has(selectedArtifactId)) {
      const fallback = displayArtifacts[0]?.filename ?? null;
      setSelectedArtifactId(fallback);
    }
  }, [displayArtifacts, artifactCount, selectedArtifactId, artifactDetails]);

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
      document.body.classList.remove("accelerator-body-lock");
      return;
    }
    document.body.classList.add("accelerator-body-lock");
    return () => {
      document.body.classList.remove("accelerator-body-lock");
    };
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

  const activeArtifact = selectedArtifactId ? artifactDetails.get(selectedArtifactId) ?? null : null;

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
        setStreaming(true);
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
                  if (payload?.type === "heartbeat") {
                    setHeartbeatAt(Date.now());
                    setStreamError(null);
                  }
                  if (payload?.type === "updates" && Array.isArray(payload?.updates)) {
                    payload.updates.forEach((update: any) => {
                      if (update?.type === "error" && typeof update.preview === "string") {
                        setStreamError(update.preview);
                      }
                    });
                  }
                  const nextArtifacts = normalizeArtifacts(payload?.artifacts ?? []);
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
                    mergeList(nextArtifacts);
                    return Array.from(map.values());
                  });
                } catch (err) {
                  console.error("Failed to parse artifact stream", err);
                }
              }
            }
            boundary = buffer.indexOf("\n\n");
          }
        }
        if (!cancelled) {
          setStreaming(false);
        }
      } catch (err) {
        if (!cancelled) {
          console.error("Artifact stream error", err);
          setStreamError("We lost connection to the artifact stream. Please retry.");
          setStreaming(false);
        }
      }
    };

    void connect();

    return () => {
      cancelled = true;
      controller.abort();
      setStreaming(false);
    };
  }, [session?.session_id, normalizeArtifacts, artifacts]);

  const handleSelectArtifact = useCallback((filename: string | null) => {
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
  }, []);

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
          setPreviewMap((prev) => ({
            ...prev,
            [selectedArtifactId]: {
              ...(prev[selectedArtifactId] ?? {
                filename: selectedArtifactId,
                version: activeArtifact?.version ?? 1,
                created_at: activeArtifact?.created_at ?? new Date().toISOString(),
                meta: activeArtifact
                  ? {
                      title: activeArtifact.title,
                      language: activeArtifact.language,
                      type: activeArtifact.type,
                      version: activeArtifact.version,
                    }
                  : undefined,
              }),
              content: html,
            },
          }));
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

  const htmlIframeUrl = useMemo(() => {
    if (!selectedPreview || previewMode !== "render") return null;
    const iframePath = selectedPreviewMeta?.iframe_url;
    if (typeof iframePath !== "string" || !iframePath) return null;
    if (iframePath.startsWith("http")) return iframePath;
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

  const hasRenderContent = previewHtml.trim().length > 0;
  const hasSourceContent = previewSource.trim().length > 0;
  const sourceText = hasSourceContent ? previewSource : previewHtml;
  const renderContent = useMemo(() => {
    if (selectedIsHtml) return previewHtml;
    return previewHtml || previewSource;
  }, [selectedIsHtml, previewHtml, previewSource]);

  const frameHeight = useMemo(() => {
    if (previewMode !== "render" || !selectedIsHtml) return null;
    if (htmlIframeUrl) return Math.max(previewHeight, 520);
    if (previewHtml.trim()) return Math.max(previewHeight, 840);
    return 640;
  }, [previewMode, selectedIsHtml, htmlIframeUrl, previewHeight, previewHtml]);

  const displayTitle =
    activeArtifact?.title ||
    activeArtifact?.filename ||
    selectedPreview?.filename ||
    (previewHtml ? "Draft preview" : "");
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

  useEffect(() => {
    if (!actionStatus) return;
    const timeout = window.setTimeout(() => setActionStatus(null), 2400);
    return () => window.clearTimeout(timeout);
  }, [actionStatus]);

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

  const latestAssistantMessageId = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const candidate = messages[index];
      if (candidate?.role === "assistant") {
        return candidate.message_id;
      }
    }
    return null;
  }, [messages]);

  const activeSwitcherLabel = useMemo(() => {
    if (!selectedArtifactId) return "Artifacts";
    const current = artifactDetails.get(selectedArtifactId);
    return current?.title || current?.filename || selectedArtifactId;
  }, [artifactDetails, selectedArtifactId]);

  const showPreviewPanel = Boolean(hasRenderContent || hasSourceContent || selectedPreview);

  const refreshSession = useCallback(async (id: string) => {
    try {
      const fresh = await getAcceleratorSession(id);
      setData(fresh);
      setPromotionProjectId(fresh.session.project_id ?? null);
    } catch (e: any) {
      setError(e?.message || "Unable to refresh session.");
    }
  }, []);

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

      try {
        const providerOverride = selectedModelOption?.available ? selectedModelOption.provider : null;
        const modelOverride = selectedModelOption?.available ? selectedModelOption.model : null;
        trackEvent("accelerator_prompt_sent", {
          sessionId: session.session_id,
          intentId: intent?.intent_id,
          length: content.length,
          model: modelOverride,
          provider: providerOverride,
        });
        await postAcceleratorMessage(session.session_id, content, {
          provider: providerOverride,
          model: modelOverride,
        });
        void refreshSession(session.session_id);
      } catch (e: any) {
        setError(e?.message || "Unable to send message right now.");
        if (!override) {
          setDraft(messageToSend);
        }
      } finally {
        setSending(false);
      }
    },
    [session, sending, draft, intent?.intent_id, refreshSession, selectedModelOption],
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
          {streamError}
        </div>
      ) : null}
      {streaming && !streamError ? (
        <div className="accelerator-status" role="status">
          <span className="accelerator-spinner" aria-hidden="true" /> Generating artifacts…
        </div>
      ) : null}

      <main className="accelerator-main" aria-live="polite">
        <section className="accelerator-chat" aria-label="Conversation">
          {loading && !session && <div className="accelerator-status">Loading accelerator…</div>}
          {!loading && session && (
            <>
              <ol className="accelerator-messages">
                {messages.map((message) => {
                  const isAssistant = message.role === "assistant";
                  const showArtifactsInline =
                    isAssistant &&
                    message.message_id === latestAssistantMessageId &&
                    displayArtifacts.length > 0;

                  const assistantDisplay = intent?.title ?? "Assistant";
                  const assistantInitials = assistantDisplay
                    .split(/\s+/)
                    .map((part) => part[0])
                    .join("")
                    .slice(0, 2)
                    .toUpperCase();

                  return (
                    <li
                      key={message.message_id}
                      className={`accelerator-message accelerator-message--${message.role}`}
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
                        <MarkdownMessage>{message.content}</MarkdownMessage>
                      </div>
                      {showArtifactsInline ? (
                        <div className="accelerator-inline-artifact-card" aria-label="Generated artifacts">
                          <header className="accelerator-inline-artifact-card__header">
                            <span className="accelerator-inline-artifact-card__label">Generated artifacts</span>
                            <span className="accelerator-inline-artifact-card__count">
                              {displayArtifacts.length} files
                            </span>
                          </header>
                          <ul className="accelerator-inline-artifact-card__list" role="list">
                            {displayArtifacts.map((artifact) => {
                              const active = selectedArtifactId === artifact.filename;
                              const extension = artifact.filename?.split(".").pop()?.toUpperCase() ?? "";
                              return (
                                <li
                                  key={`${artifact.filename}-${artifact.version ?? "v"}`}
                                  className={
                                    active
                                      ? "accelerator-inline-artifact-card__item accelerator-inline-artifact-card__item--active"
                                      : "accelerator-inline-artifact-card__item"
                                  }
                                >
                                  <button
                                    type="button"
                                    className="accelerator-inline-artifact-card__button"
                                    onClick={() => handleSelectArtifact(artifact.filename)}
                                    aria-pressed={active}
                                  >
                                    <span className="accelerator-inline-artifact-card__icon" aria-hidden="true">
                                      {extension}
                                    </span>
                                    <span className="accelerator-inline-artifact-card__text">
                                      <span className="accelerator-inline-artifact-card__title">
                                        {artifact.title || artifact.filename}
                                      </span>
                                      <span className="accelerator-inline-artifact-card__meta">
                                        {extension || "FILE"}
                                        {artifact.version ? ` • v${artifact.version}` : ""}
                                      </span>
                                    </span>
                                  </button>
                                  <button
                                    type="button"
                                    className="accelerator-inline-artifact-card__download"
                                    onClick={() => void downloadArtifact(artifact.filename)}
                                    aria-label={`Download ${artifact.title || artifact.filename}`}
                                  >
                                    Download
                                  </button>
                                </li>
                              );
                            })}
                          </ul>
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ol>
              <div ref={messagesEndRef} />
            </>
          )}
        </section>

      </main>

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
        sendIcon={<span aria-hidden="true">↑</span>}
      />
      {displayArtifacts.length > 0 ? (
        <button
          type="button"
          className="accelerator-drawer-toggle"
          onClick={() => {
            setDrawerOpen((open) => {
              const nextOpen = !open;
              if (!nextOpen) {
                setDrawerExpanded(false);
                setArtifactMenuOpen(false);
              }
              return nextOpen;
            });
          }}
          aria-pressed={drawerOpen}
          aria-label={drawerOpen ? "Hide generated artifacts" : `Show generated artifacts (${displayArtifacts.length})`}
        >
          <span aria-hidden="true">☰</span>
        </button>
      ) : null}
      <div
        className={`accelerator-drawer${drawerOpen ? " accelerator-drawer--open" : ""}${
          drawerExpanded ? " accelerator-drawer--expanded" : ""
        }`}
      >
        <div
          className="accelerator-drawer__backdrop"
          role="presentation"
          onClick={() => {
            setDrawerOpen(false);
            setDrawerExpanded(false);
            setArtifactMenuOpen(false);
            setPreviewActionsOpen(false);
          }}
        />
        <aside className="accelerator-drawer__panel" aria-label="Artifact preview">
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
                            <span className="accelerator-drawer__menu-item-title">
                              {artifact.title || artifact.filename}
                            </span>
                            {artifact.version ? (
                              <span className="accelerator-drawer__menu-item-meta">v{artifact.version}</span>
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
                Close
              </button>
            </div>
          </header>
          <div className="accelerator-drawer__content">
            <div className="accelerator-drawer__body" aria-live="polite">
              {showPreviewPanel ? (
                <div className="accelerator-preview-card">
                  <header className="accelerator-preview-card__header">
                    <div className="accelerator-preview-card__header-left">
                      <div className="accelerator-preview-card__toggles">
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
                          aria-label="Show final output"
                        >
                          <span className="accelerator-preview-toggle__icon" aria-hidden="true">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7Z" />
                              <circle cx="12" cy="12" r="3.5" />
                            </svg>
                          </span>
                          <span className="sr-only">Final output</span>
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
                          aria-label="Show source"
                        >
                          <span className="accelerator-preview-toggle__icon" aria-hidden="true">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                              <polyline points="16 18 22 12 16 6" />
                              <polyline points="8 6 2 12 8 18" />
                            </svg>
                          </span>
                          <span className="sr-only">Source</span>
                        </button>
                      </div>
                    </div>
                    <div className="accelerator-preview-card__header-actions" ref={previewActionsRef}>
                      <button
                        type="button"
                        className="accelerator-preview-card__action"
                        onClick={() => {
                          if (!(previewMode === "source" ? sourceText : previewHtml).trim()) return;
                          setPreviewActionsOpen((open) => !open);
                        }}
                        disabled={!(previewMode === "source" ? sourceText : previewHtml).trim()}
                        aria-expanded={previewActionsOpen}
                        aria-haspopup="menu"
                      >
                        <span className="accelerator-preview-card__action-label">Copy</span>
                        <span className="accelerator-preview-card__action-caret" aria-hidden="true" />
                      </button>
                      {previewActionsOpen ? (
                        <div className="accelerator-preview-card__action-menu" role="menu">
                          <button
                            type="button"
                            role="menuitem"
                            onClick={() => {
                              handleCopyPreview();
                              setPreviewActionsOpen(false);
                            }}
                            disabled={!(previewMode === "source" ? sourceText : previewHtml).trim()}
                          >
                            Copy text
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
                            Download
                          </button>
                        </div>
                      ) : null}
                      <button
                        type="button"
                        className="accelerator-preview-card__icon-button"
                        onClick={() => handleDownloadPreview()}
                        disabled={!selectedArtifactId}
                        aria-label="Download artifact"
                      >
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                          <polyline points="7 10 12 15 17 10" />
                          <line x1="12" y1="15" x2="12" y2="3" />
                        </svg>
                      </button>
                    </div>
                  </header>
                  {actionStatus ? <div className="accelerator-preview-card__status">{actionStatus}</div> : null}
                  <div className="accelerator-preview-card__body">
                    {previewMode === "render" ? (
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
                            />
                          </div>
                        ) : (
                          <div className="accelerator-preview-card__empty">Preview not available for this artifact.</div>
                        )
                      ) : (
                        <div className="accelerator-preview-card__markdown">
                          <MarkdownMessage className="accelerator-preview-card__content">
                            {renderContent || ""}
                          </MarkdownMessage>
                        </div>
                      )
                    ) : sourceText.trim() ? (
                      <pre className="accelerator-preview-card__source" aria-label="Source code">
                        <code>{sourceText}</code>
                      </pre>
                    ) : (
                      <div className="accelerator-preview-card__empty">
                        Source view is unavailable for this artifact.
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="accelerator-preview-card accelerator-preview-card--empty">
                  Select an artifact to preview the final experience.
                </div>
              )}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
