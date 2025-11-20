import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { API_BASE_URL, DocumentArtifact, getAccessToken, trackEvent } from "./api";

export interface ProjectDocumentRecord extends DocumentArtifact {
  filename: string;
  content: string;
  meta?: Record<string, any> | null;
  version?: number;
  created_at?: string;
  revision?: number;
}

export interface ProjectDocumentStatus {
  message: string;
  stage?: string | null;
  progress?: number | null;
  ts?: string;
}

export interface ProjectDocumentStreamState {
  documents: ProjectDocumentRecord[];
  documentMap: Record<string, ProjectDocumentRecord>;
  latestRevision: number;
  livePreview: string;
  status: ProjectDocumentStatus | null;
  heartbeatAt: number | null;
  streaming: boolean;
  hasSnapshot: boolean;
  streamError: string | null;
  isConnected: boolean;
  reconnect: () => void;
  disconnect: () => void;
  recentUpdates: ProjectDocumentStreamUpdate[];
}

export interface ProjectDocumentStreamUpdate {
  type: "document_update" | "draft_update" | "status" | "error";
  filename?: string;
  section?: string | null;
  messageId?: string | null;
  message?: string | null;
  summary?: string | null;
  changeDescription?: string | null;
  diff?: string | null;
  version?: number | null;
  revision?: number | null;
  stage?: string | null;
  progress?: number | null;
  preview?: string | null;
  source?: string | null;
  ts?: string | null;
}

interface BaseStreamEvent {
  type: string;
  revision?: number;
  ts?: string;
}

interface SnapshotEvent extends BaseStreamEvent {
  type: "snapshot";
  artifacts: ProjectDocumentRecord[];
}

interface DocumentUpdatePayload {
  type: string;
  filename?: string;
  content?: string;
  meta?: Record<string, any> | null;
  source?: string;
  revision?: number;
  section?: string | null;
  message_id?: string | null;
  preview?: string;
  message?: string;
  stage?: string;
  progress?: number;
  summary?: string | null;
  change_description?: string | null;
  diff?: string | null;
  version?: number;
}

interface UpdatesEvent extends BaseStreamEvent {
  type: "updates";
  updates: DocumentUpdatePayload[];
  latest_revision?: number;
}

interface HeartbeatEvent extends BaseStreamEvent {
  type: "heartbeat";
}

type StreamEvent = SnapshotEvent | UpdatesEvent | HeartbeatEvent;

interface ConnectOptions {
  projectId?: string | null;
  startRevision?: number;
  autostart?: boolean;
}

function normaliseArtifacts(list: any): ProjectDocumentRecord[] {
  if (!Array.isArray(list)) return [];
  return list
    .map((item) => {
      if (!item) return null;
      const record: ProjectDocumentRecord = {
        filename: String(item.filename ?? ""),
        content: String(item.content ?? ""),
        meta: (item.meta ?? null) as Record<string, any> | null,
        version: typeof item.version === "number" ? item.version : undefined,
        created_at: typeof item.created_at === "string" ? item.created_at : undefined,
        revision: typeof item.revision === "number" ? item.revision : undefined,
        path: typeof item.path === "string" ? item.path : undefined,
      };
      if (!record.filename) return null;
      return record;
    })
    .filter((item): item is ProjectDocumentRecord => !!item);
}

function parseEvent(raw: string): StreamEvent | null {
  try {
    const data = JSON.parse(raw);
    if (!data || typeof data.type !== "string") return null;
    if (data.type === "snapshot") {
      return {
        type: "snapshot",
        revision: typeof data.revision === "number" ? data.revision : undefined,
        artifacts: normaliseArtifacts(data.artifacts),
        ts: typeof data.ts === "string" ? data.ts : undefined,
      };
    }
    if (data.type === "updates") {
      return {
        type: "updates",
        updates: Array.isArray(data.updates) ? data.updates : [],
        latest_revision: typeof data.latest_revision === "number" ? data.latest_revision : undefined,
        revision: typeof data.revision === "number" ? data.revision : undefined,
        ts: typeof data.ts === "string" ? data.ts : undefined,
      };
    }
    if (data.type === "heartbeat") {
      return {
        type: "heartbeat",
        revision: typeof data.revision === "number" ? data.revision : undefined,
        ts: typeof data.ts === "string" ? data.ts : undefined,
      };
    }
    return null;
  } catch (err) {
    console.error("project_document_stream_parse_error", err);
    return null;
  }
}

function toRecordMap(items: ProjectDocumentRecord[]): Record<string, ProjectDocumentRecord> {
  const next: Record<string, ProjectDocumentRecord> = {};
  items.forEach((item) => {
    next[item.filename] = item;
  });
  return next;
}

export function useProjectDocumentStream(options: ConnectOptions): ProjectDocumentStreamState;
export function useProjectDocumentStream(projectId: string | null | undefined, startRevision?: number): ProjectDocumentStreamState;
export function useProjectDocumentStream(
  arg1: ConnectOptions | (string | null | undefined),
  arg2?: number,
): ProjectDocumentStreamState {
  const opts: ConnectOptions =
    typeof arg1 === "object" && arg1 !== null && !(arg1 instanceof String)
      ? arg1
      : { projectId: arg1 as string | null | undefined, startRevision: arg2 };

  const { projectId = null, startRevision, autostart = true } = opts;

  const [documentsVersion, setDocumentsVersion] = useState(0);
  const documentsRef = useRef<Record<string, ProjectDocumentRecord>>({});
  const [latestRevision, setLatestRevision] = useState(0);
  const [livePreview, setLivePreview] = useState("");
  const [status, setStatus] = useState<ProjectDocumentStatus | null>(null);
  const [heartbeatAt, setHeartbeatAt] = useState<number | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [streaming, setStreaming] = useState<boolean>(false);
  const [hasSnapshot, setHasSnapshot] = useState<boolean>(false);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const controllerRef = useRef<AbortController | null>(null);
  const reconnectSeqRef = useRef(0);
  const [connectSeq, setConnectSeq] = useState(0);
  const updatesRef = useRef<ProjectDocumentStreamUpdate[]>([]);
  const [updatesVersion, setUpdatesVersion] = useState(0);
  const lastHeartbeatRef = useRef<number | null>(null);

  const bumpDocumentsVersion = useCallback(() => {
    setDocumentsVersion((prev) => prev + 1);
  }, []);

  const recordUpdate = useCallback((entry: ProjectDocumentStreamUpdate) => {
    updatesRef.current = [...updatesRef.current.slice(-49), entry];
    setUpdatesVersion((prev) => prev + 1);
  }, []);

  const disconnect = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setStreaming(false);
    setIsConnected(false);
  }, []);

  const reconnect = useCallback(() => {
    disconnect();
    reconnectSeqRef.current += 1;
    setConnectSeq((prev) => prev + 1);
  }, [disconnect]);

  const applySnapshot = useCallback((event: SnapshotEvent) => {
    documentsRef.current = toRecordMap(event.artifacts);
    bumpDocumentsVersion();
    setLatestRevision(event.revision ?? 0);
    setHasSnapshot(true);
    setStreaming(false);
  }, [bumpDocumentsVersion]);

  const applyUpdates = useCallback(
    (event: UpdatesEvent) => {
      if (!event.updates || event.updates.length === 0) return;
      const current = { ...documentsRef.current };
      let dirty = false;
      event.updates.forEach((update) => {
        if (!update || typeof update.type !== "string") return;
        switch (update.type) {
          case "document_update": {
            const filename = update.filename ?? "";
            if (!filename) break;
            const existing = current[filename];
            const nextRecord: ProjectDocumentRecord = {
              filename,
              content: typeof update.content === "string" ? update.content : existing?.content ?? "",
              meta: update.meta ?? existing?.meta ?? null,
              version:
                typeof update.version === "number"
                  ? update.version
                  : typeof update.meta?.version === "number"
                    ? update.meta.version
                    : existing?.version,
              created_at: existing?.created_at,
              revision: typeof update.revision === "number" ? update.revision : existing?.revision,
            };
            current[filename] = nextRecord;
            dirty = true;
            recordUpdate({
              type: "document_update",
              filename,
              section:
                typeof update.section === "string"
                  ? update.section
                  : typeof update.meta?.section === "string"
                    ? update.meta.section
                    : null,
              messageId:
                typeof update.message_id === "string"
                  ? update.message_id
                  : typeof update.meta?.message_id === "string"
                    ? update.meta.message_id
                    : null,
              message: typeof update.message === "string" ? update.message : null,
              summary:
                typeof update.summary === "string"
                  ? update.summary
                  : typeof update.meta?.summary === "string"
                    ? update.meta.summary
                    : null,
              changeDescription:
                typeof update.change_description === "string"
                  ? update.change_description
                  : typeof update.meta?.change_description === "string"
                    ? update.meta.change_description
                    : null,
              diff: typeof update.diff === "string" ? update.diff : null,
              version:
                typeof nextRecord.version === "number"
                  ? nextRecord.version
                  : typeof update.version === "number"
                    ? update.version
                    : null,
              revision: typeof nextRecord.revision === "number" ? nextRecord.revision : null,
              stage: typeof update.stage === "string" ? update.stage : null,
              progress:
                typeof update.progress === "number"
                  ? update.progress
                  : typeof update.meta?.progress === "number"
                    ? update.meta.progress
                    : null,
              source: typeof update.source === "string" ? update.source : null,
              ts: event.ts ?? new Date().toISOString(),
            });
            break;
          }
          case "draft_update": {
            if (typeof update.preview === "string") {
              setLivePreview(update.preview);
              setStreaming(true);
            }
            recordUpdate({
              type: "draft_update",
              filename: typeof update.filename === "string" ? update.filename : undefined,
              preview: typeof update.preview === "string" ? update.preview : null,
              ts: event.ts ?? new Date().toISOString(),
            });
            break;
          }
          case "status": {
            setStatus({
              message: typeof update.message === "string" ? update.message : "",
              stage: typeof update.stage === "string" ? update.stage : null,
              progress: typeof update.progress === "number" ? update.progress : null,
              ts: event.ts,
            });
            recordUpdate({
              type: "status",
              message: typeof update.message === "string" ? update.message : null,
              stage: typeof update.stage === "string" ? update.stage : null,
              progress: typeof update.progress === "number" ? update.progress : null,
              ts: event.ts ?? new Date().toISOString(),
            });
            break;
          }
          case "error": {
            if (typeof update.message === "string") {
              setStreamError(update.message);
            } else if (typeof update.preview === "string") {
              setStreamError(update.preview);
            }
            recordUpdate({
              type: "error",
              message:
                typeof update.message === "string"
                  ? update.message
                  : typeof update.preview === "string"
                    ? update.preview
                    : null,
              ts: event.ts ?? new Date().toISOString(),
            });
            break;
          }
          default:
            break;
        }
      });
      if (dirty) {
        documentsRef.current = current;
        bumpDocumentsVersion();
      }
      if (typeof event.latest_revision === "number") {
        setLatestRevision(event.latest_revision);
      } else if (event.revision) {
        setLatestRevision(event.revision);
      }
    },
    [bumpDocumentsVersion, recordUpdate],
  );

  useEffect(() => {
    if (!projectId || !autostart) {
      return;
    }

    let cancelled = false;
    const seqAtStart = reconnectSeqRef.current;
    const controller = new AbortController();
    controllerRef.current = controller;

    async function connect() {
      try {
        const resolvedProjectId = projectId as string;
        const url = new URL(
          `${API_BASE_URL}/projects/${encodeURIComponent(resolvedProjectId)}/documents/stream`,
        );
        if (typeof startRevision === "number" && Number.isFinite(startRevision)) {
          url.searchParams.set("starting_revision", String(startRevision));
        }
        const token = getAccessToken();
        const connectStartedAt = Date.now();
        const res = await fetch(url.toString(), {
          method: "GET",
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          signal: controller.signal,
        });
        if (!res.ok || !res.body) {
          setStreamError(`Stream connection failed (${res.status})`);
          setIsConnected(false);
          if (projectId) {
            trackEvent("project_document_stream_connect_failed", {
              projectId: projectId,
              status: res.status,
            });
          }
          return;
        }
        setIsConnected(true);
        setStreamError(null);
        if (projectId) {
          trackEvent("project_document_stream_connected", {
            projectId: projectId,
            latency_ms: Date.now() - connectStartedAt,
          });
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!cancelled) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          while (parts.length > 1) {
            const chunk = parts.shift() as string;
            const dataLine = chunk
              .split("\n")
              .map((line) => line.trim())
              .find((line) => line.startsWith("data:"));
            if (dataLine) {
              const raw = dataLine.replace(/^data:\s*/, "");
              if (!raw) continue;
              const event = parseEvent(raw);
              if (!event) continue;
              switch (event.type) {
                case "snapshot":
                  applySnapshot(event);
                  break;
                case "updates":
                  applyUpdates(event);
                  break;
                case "heartbeat":
                  {
                    const now = Date.now();
                    if (projectId && lastHeartbeatRef.current !== null) {
                      const delta = now - lastHeartbeatRef.current;
                      trackEvent("project_document_stream_heartbeat", {
                        projectId: projectId,
                        delta_ms: delta,
                      });
                    }
                    lastHeartbeatRef.current = now;
                  }
                  setHeartbeatAt(Date.now());
                  setStreaming((prev) => prev); // keep existing state
                  break;
                default:
                  break;
              }
            }
            buffer = parts.join("\n\n");
          }
        }
      } catch (err) {
        if (!cancelled) {
          console.error("project_document_stream_error", err);
          setStreamError(err instanceof Error ? err.message : String(err));
          setIsConnected(false);
          if (projectId) {
            trackEvent("project_document_stream_exception", {
              projectId: projectId,
              message: err instanceof Error ? err.message : String(err),
            });
          }
        }
      } finally {
        if (!cancelled) {
          setStreaming(false);
        }
      }
    }

    connect().catch((err) => {
      console.error("project_document_stream_unhandled", err);
      setStreamError(err instanceof Error ? err.message : String(err));
      setIsConnected(false);
    });

    return () => {
      cancelled = true;
      controller.abort();
      if (seqAtStart === reconnectSeqRef.current) {
        controllerRef.current = null;
      }
    };
  }, [projectId, startRevision, autostart, applySnapshot, applyUpdates, connectSeq]);

  const documents = useMemo(() => {
    const list = Object.values(documentsRef.current);
    return list.sort((a, b) => a.filename.localeCompare(b.filename));
  }, [documentsVersion]);

  const documentMap = useMemo(() => ({ ...documentsRef.current }), [documentsVersion]);
  const recentUpdates = useMemo(
    () => updatesRef.current.slice(-20),
    [updatesVersion],
  );

  return {
    documents,
    documentMap,
    latestRevision,
    livePreview,
    status,
    heartbeatAt,
    streaming,
    hasSnapshot,
    streamError,
    isConnected,
    reconnect,
    disconnect,
    recentUpdates,
  };
}
