export interface Project {
  project_id: string;
  name: string;
  description: string;
  status: string;
  current_phase: string;
  created_at: string;
  updated_at?: string;
  metadata?: Record<string, any>;
}

export async function enrichProject(
  project_id: string,
  prompt: string,
): Promise<EnrichResponse> {
  const res = await apiFetch(`${API_BASE}/projects/${project_id}/enrich`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  return res.json();
}

export interface ProjectCreate {
  name: string;
  description: string;
  type?: string | null;
  methodology?: string | null;
  features?: string | null;
}

export interface DocumentArtifact {
  filename: string;
  content: string;
  path?: string;
}

export interface DocGenResponse {
  project_id: string;
  saved_to?: string;
  artifacts: DocumentArtifact[];
}

export interface DocGenOptions {
  traceability_overlay?: boolean;
  paste_requirements?: string;
  answers?: Record<string, string[]>;
  summaries?: Record<string, string>;
}

export interface EnrichResponse {
  answers: Record<string, string[]>;
  summaries: Record<string, string>;
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const PUBLIC_MODE =
  process.env.NEXT_PUBLIC_PUBLIC_MODE === "1" ||
  process.env.NEXT_PUBLIC_PUBLIC_MODE === "true";
const MVP_SERVICE_TOKEN = process.env.NEXT_PUBLIC_MVP_SERVICE_TOKEN || "";
export const TOKEN_CHANGE_EVENT = "opnxt-token-change";
const TELEMETRY_ENDPOINT = `${API_BASE}/telemetry/events`;
const TELEMETRY_SOURCE = "web-app";

// --- Auth models ---
export interface User {
  email: string;
  name: string;
  roles: string[];
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface OTPRequestResponse {
  status: string;
  expires_in: number;
  code?: string;
}

// --- Token storage (dev: localStorage + in-memory) ---
let accessToken: string | null = null;
try {
  const t =
    typeof window !== "undefined"
      ? window.localStorage.getItem("opnxt_token")
      : null;
  if (t) accessToken = t;
} catch {}

// In public mode, ensure no token is used
if (PUBLIC_MODE) {
  accessToken = null;
  try {
    if (typeof window !== "undefined")
      window.localStorage.removeItem("opnxt_token");
  } catch {}
}

export function setAccessToken(token: string | null) {
  accessToken = token;
  try {
    if (typeof window !== "undefined") {
      if (token) window.localStorage.setItem("opnxt_token", token);
      else window.localStorage.removeItem("opnxt_token");
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: "opnxt_token",
          newValue: token ?? null,
        }),
      );
      window.dispatchEvent(
        new CustomEvent(TOKEN_CHANGE_EVENT, { detail: { token } }),
      );
    }
  } catch {}
}

export function getAccessToken() {
  if (!accessToken && typeof window !== "undefined") {
    try {
      const stored = window.localStorage.getItem("opnxt_token");
      if (stored) accessToken = stored;
    } catch {}
  }
  return accessToken;
}

export class ApiError extends Error {
  status?: number;
}

function isMvpRoute(): boolean {
  try {
    if (typeof window === "undefined") return false;
    const path = window.location?.pathname || "";
    if (path === "/" || path === "/mvp" || path.startsWith("/mvp/"))
      return true;
    return path === "/start" || path.startsWith("/start/");
  } catch {
    return false;
  }
}

async function apiFetch(
  input: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers: Record<string, string> = { ...(init.headers as any) };
  const token = getAccessToken();
  const guestContext = (PUBLIC_MODE || isMvpRoute()) && !token;
  if (!guestContext && token) {
    headers["Authorization"] = `Bearer ${token}`;
  } else if (guestContext && MVP_SERVICE_TOKEN) {
    headers["Authorization"] = `Bearer ${MVP_SERVICE_TOKEN}`;
  }
  let res = await fetch(input, { ...init, headers });
  if (!res.ok) {
    const err = new ApiError(`HTTP ${res.status}`);
    err.status = res.status;
    try {
      const data = await res.json();
      if (data?.detail) err.message = data.detail;
    } catch {}
    // If public or MVP route and we hit an auth error with a lingering token, clear and retry once without Authorization
    if (
      (PUBLIC_MODE || isMvpRoute()) &&
      (res.status === 401 || res.status === 403)
    ) {
      try {
        setAccessToken(null);
      } catch {}
      const h2: Record<string, string> = { ...(init.headers as any) };
      delete h2["Authorization"];
      res = await fetch(input, { ...init, headers: h2 });
      if (res.ok) return res;
    }
    throw err;
  }
  return res;
}

export async function listProjects(): Promise<Project[]> {
  const res = await apiFetch(`${API_BASE}/projects`, { cache: "no-store" });
  return res.json();
}

export async function getProject(project_id: string): Promise<Project> {
  const res = await apiFetch(`${API_BASE}/projects/${project_id}`, {
    cache: "no-store",
  });
  return res.json();
}

export async function createProject(payload: ProjectCreate): Promise<Project> {
  const res = await apiFetch(`${API_BASE}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function advanceProject(project_id: string): Promise<Project> {
  const res = await apiFetch(`${API_BASE}/projects/${project_id}/advance`, {
    method: "PUT",
  });
  return res.json();
}

export async function deleteProject(project_id: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/projects/${project_id}`, {
    method: "DELETE",
  });
}

export function isFinalPhase(phase: string): boolean {
  return phase?.toLowerCase() === "end";
}

export async function generateDocuments(
  project_id: string,
  opts?: DocGenOptions,
): Promise<DocGenResponse> {
  const res = await apiFetch(`${API_BASE}/projects/${project_id}/documents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: opts ? JSON.stringify(opts) : undefined,
  });
  return res.json();
}

export function artifactUrl(project_id: string, filename: string): string {
  const base = API_BASE.replace(/\/$/, "");
  return `${base}/files/generated/${encodeURIComponent(project_id)}/${encodeURIComponent(filename)}`;
}

export function zipUrl(project_id: string): string {
  const base = API_BASE.replace(/\/$/, "");
  return `${base}/projects/${encodeURIComponent(project_id)}/documents.zip`;
}

export function documentDownloadUrl(
  project_id: string,
  filename: string,
  version?: number,
): string {
  const base = API_BASE.replace(/\/$/, "");
  const v = typeof version === "number" ? `?version=${version}` : "";
  return `${base}/projects/${encodeURIComponent(project_id)}/documents/${encodeURIComponent(filename)}/download${v}`;
}

export function documentDocxUrl(
  project_id: string,
  filename: string,
  version?: number,
): string {
  const base = API_BASE.replace(/\/$/, "");
  const v = typeof version === "number" ? `?version=${version}` : "";
  return `${base}/projects/${encodeURIComponent(project_id)}/documents/${encodeURIComponent(filename)}/docx${v}`;
}

export async function requestOtp(email: string): Promise<OTPRequestResponse> {
  const res = await fetch(`${API_BASE}/auth/request-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    const err = new ApiError(`OTP request failed (${res.status})`);
    try {
      const data = await res.json();
      if (data?.detail) {
        if (typeof data.detail === "string") {
          err.message = data.detail;
        } else if (Array.isArray(data.detail)) {
          err.message = data.detail
            .map((item: any) => item?.msg || item?.type || JSON.stringify(item))
            .join("; ");
        } else {
          err.message = JSON.stringify(data.detail);
        }
      }
    } catch {}
    throw err;
  }
  return res.json();
}

export async function verifyOtp(email: string, code: string, name?: string): Promise<User> {
  const res = await fetch(`${API_BASE}/auth/verify-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code, ...(name ? { name } : {}) }),
  });
  if (!res.ok) {
    const err = new ApiError(`OTP verification failed (${res.status})`);
    try {
      const data = await res.json();
      if (data?.detail) {
        if (typeof data.detail === "string") err.message = data.detail;
        else if (Array.isArray(data.detail))
          err.message = data.detail
            .map((item: any) => item?.msg || item?.type || JSON.stringify(item))
            .join("; ");
        else err.message = JSON.stringify(data.detail);
      }
    } catch {}
    throw err;
  }
  const data: TokenResponse = await res.json();
  setAccessToken(data.access_token);
  return data.user;
}

export function logout() {
  setAccessToken(null);
}

export async function me(): Promise<User> {
  const res = await apiFetch(`${API_BASE}/auth/me`);
  return res.json();
}

// --- Role helpers ---
export function hasRole(user: User | null | undefined, role: string): boolean {
  return !!user?.roles?.includes(role);
}

export function canRead(user: User | null | undefined): boolean {
  // viewer and above
  return (
    hasRole(user, "viewer") ||
    hasRole(user, "contributor") ||
    hasRole(user, "approver") ||
    hasRole(user, "admin")
  );
}

export function canWrite(user: User | null | undefined): boolean {
  return (
    hasRole(user, "contributor") ||
    hasRole(user, "approver") ||
    hasRole(user, "admin")
  );
}

export function isAdmin(user: User | null | undefined): boolean {
  return hasRole(user, "admin");
}

// --- Agents ---
export interface Agent {
  agent_id: string;
  name: string;
  description?: string;
  capabilities: string[];
  endpoint_url?: string;
  status: string;
  created_at: string;
  updated_at?: string;
}

export interface AgentCreate {
  name: string;
  description?: string;
  capabilities?: string[];
  endpoint_url?: string;
}

export interface AgentUpdate {
  name?: string;
  description?: string;
  capabilities?: string[];
  endpoint_url?: string;
  status?: string;
}

export async function listAgents(): Promise<Agent[]> {
  const res = await apiFetch(`${API_BASE}/agents`, { cache: "no-store" });
  return res.json();
}

export async function createAgent(payload: AgentCreate): Promise<Agent> {
  const res = await apiFetch(`${API_BASE}/agents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function getAgent(agent_id: string): Promise<Agent> {
  const res = await apiFetch(`${API_BASE}/agents/${agent_id}`);
  return res.json();
}

export async function updateAgent(
  agent_id: string,
  patch: AgentUpdate,
): Promise<Agent> {
  const res = await apiFetch(`${API_BASE}/agents/${agent_id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return res.json();
}

export async function deleteAgent(agent_id: string): Promise<void> {
  await apiFetch(`${API_BASE}/agents/${agent_id}`, { method: "DELETE" });
}

// --- Context & Impact ---
export interface ProjectContext {
  data: Record<string, any>;
}

export interface LeanSnapshotRequest {
  markdown_content: string;
  metadata?: Record<string, any>;
}

export interface LeanSnapshotResponse {
  message: string;
  count: number;
}

export interface ImpactItem {
  kind: string;
  name: string;
  confidence: number;
}
export interface ImpactResponse {
  project_id: string;
  impacts: ImpactItem[];
}

export async function getProjectContext(
  project_id: string,
): Promise<ProjectContext> {
  const res = await apiFetch(`${API_BASE}/projects/${project_id}/context`, {
    cache: "no-store",
  });
  return res.json();
}

export async function putProjectContext(
  project_id: string,
  ctx: ProjectContext,
): Promise<ProjectContext> {
  const res = await apiFetch(`${API_BASE}/projects/${project_id}/context`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(ctx),
  });
  return res.json();
}

export async function saveLeanSnapshot(
  project_id: string,
  snapshot: LeanSnapshotRequest,
): Promise<LeanSnapshotResponse> {
  const res = await apiFetch(
    `${API_BASE}/projects/${project_id}/context/lean-snapshot`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(snapshot),
    },
  );
  return res.json();
}

export async function computeImpacts(
  project_id: string,
  changed: string[],
): Promise<ImpactResponse> {
  const res = await apiFetch(`${API_BASE}/projects/${project_id}/impacts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ changed }),
  });
  return res.json();
}

// --- Document Versioning ---
export interface DocumentVersionInfo {
  version: number;
  created_at: string;
  meta: Record<string, any>;
}
export interface DocumentVersionsResponse {
  project_id: string;
  versions: Record<string, DocumentVersionInfo[]>;
}
export interface DocumentVersionResponse {
  filename: string;
  version: number;
  content: string;
}

export async function listDocumentVersions(
  project_id: string,
): Promise<DocumentVersionsResponse> {
  const res = await apiFetch(
    `${API_BASE}/projects/${project_id}/documents/versions`,
    { cache: "no-store" },
  );
  return res.json();
}

export async function getDocumentVersion(
  project_id: string,
  filename: string,
  version: number,
): Promise<DocumentVersionResponse> {
  const res = await apiFetch(
    `${API_BASE}/projects/${project_id}/documents/${encodeURIComponent(filename)}/versions/${version}`,
  );
  return res.json();
}

// --- AI Master Prompt Generation ---
export interface AIGenRequest {
  input_text: string;
  doc_types?: string[];
  include_backlog?: boolean;
}
export async function aiGenerateDocuments(
  project_id: string,
  req: AIGenRequest,
): Promise<DocGenResponse> {
  const res = await apiFetch(`${API_BASE}/projects/${project_id}/ai-docs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`AI generation failed: ${res.status} ${text}`);
  }
  return res.json();
}

// --- Diagnostics ---
export interface DiagLLM {
  provider: string;
  has_api_key: boolean;
  base_url: string;
  model: string;
  library_present: boolean;
  ready: boolean;
}
export async function diagLLM(): Promise<DiagLLM> {
  const res = await apiFetch(`${API_BASE}/diag/llm`, { cache: "no-store" });
  return res.json();
}

export interface LLMUpdateRequest {
  provider?: string;
  base_url?: string;
  model?: string;
}
export async function updateLLMSettings(
  patch: LLMUpdateRequest,
): Promise<DiagLLM> {
  const res = await apiFetch(`${API_BASE}/diag/llm`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch || {}),
  });
  return res.json();
}

// --- Chat ---
export interface ChatSession {
  session_id: string;
  project_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  created_by: string;
}

export interface ChatMessage {
  message_id: string;
  session_id: string;
  role: "system" | "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ChatSessionWithMessages {
  session: ChatSession;
  messages: ChatMessage[];
}

export async function listChatSessions(
  project_id: string,
): Promise<ChatSession[]> {
  const res = await apiFetch(
    `${API_BASE}/chat/sessions?project_id=${encodeURIComponent(project_id)}`,
    { cache: "no-store" },
  );
  return res.json();
}

export async function createChatSession(
  project_id: string,
  title?: string,
): Promise<ChatSession> {
  const res = await apiFetch(`${API_BASE}/chat/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id, title }),
  });
  return res.json();
}

export async function getChatSession(
  session_id: string,
): Promise<ChatSessionWithMessages> {
  const res = await apiFetch(
    `${API_BASE}/chat/sessions/${encodeURIComponent(session_id)}`,
    { cache: "no-store" },
  );
  return res.json();
}

export async function listChatMessages(
  session_id: string,
): Promise<ChatMessage[]> {
  const res = await apiFetch(
    `${API_BASE}/chat/sessions/${encodeURIComponent(session_id)}/messages`,
    { cache: "no-store" },
  );
  return res.json();
}

export async function postChatMessage(
  session_id: string,
  content: string,
): Promise<ChatMessage> {
  const res = await apiFetch(
    `${API_BASE}/chat/sessions/${encodeURIComponent(session_id)}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    },
  );
  return res.json();
}

// --- Uploads / Ingestion ---
export interface UploadAnalyzeItem {
  filename: string;
  text_length: number;
  requirements: string[];
}
export interface UploadAnalyzeResponse {
  project_id: string;
  items: UploadAnalyzeItem[];
}
export interface UploadApplyRequest {
  requirements: string[];
  category?: string;
  append_only?: boolean;
}

// --- Catalog ---
export interface CatalogIntent {
  intent_id: string;
  title: string;
  group: string;
  description: string;
  prefill_prompt: string;
  deliverables: string[];
  personas: string[];
  guardrails: string[];
  icon?: string | null;
  requirement_area?: string | null;
  core_functionality?: string | null;
  opnxt_benefit?: string | null;
}

export function formatCatalogIntentPrompt(intent: CatalogIntent): string {
  const lines: string[] = [];
  lines.push(`Accelerator: ${intent.title}`);
  lines.push(`Goal: ${intent.description}`);
  if (intent.deliverables?.length) {
    lines.push(`Target outputs: ${intent.deliverables.join(", ")}`);
  }
  if (intent.guardrails?.length) {
    lines.push(`Guardrails to respect: ${intent.guardrails.join(", ")}`);
  }
  if (intent.requirement_area) {
    lines.push(`Requirement focus: ${intent.requirement_area}`);
  }
  if (intent.opnxt_benefit) {
    lines.push(`OPNXT benefit: ${intent.opnxt_benefit}`);
  }
  if (intent.core_functionality) {
    lines.push(`Core functionality: ${intent.core_functionality}`);
  }
  lines.push(intent.prefill_prompt.trim());
  return lines.filter(Boolean).join("\n\n");
}

type CatalogCacheEntry = {
  data: CatalogIntent[];
  fetchedAt: number;
};

const CATALOG_CACHE_TTL_MS = 1000 * 60 * 5; // 5 minutes
const catalogCache = new Map<string, CatalogCacheEntry>();
const catalogPending = new Map<string, Promise<CatalogIntent[]>>();

export function clearCatalogCache() {
  catalogCache.clear();
  catalogPending.clear();
}

// --- Accelerator sessions ---
export interface AcceleratorSession {
  session_id: string;
  accelerator_id: string;
  created_by: string;
  created_at: string;
  persona?: string | null;
  project_id?: string | null;
  promoted_at?: string | null;
  metadata?: Record<string, any>;
}

export interface AcceleratorMessage {
  message_id: string;
  session_id: string;
  role: "assistant" | "user" | "system";
  content: string;
  created_at: string;
}

export interface LaunchAcceleratorResponse {
  session: AcceleratorSession;
  intent: CatalogIntent;
  messages: AcceleratorMessage[];
}

export async function launchAcceleratorSession(
  intentId: string,
): Promise<LaunchAcceleratorResponse> {
  const res = await apiFetch(`${API_BASE}/accelerators/${intentId}/sessions`, {
    method: "POST",
  });
  return res.json();
}

export async function getAcceleratorSession(
  sessionId: string,
): Promise<LaunchAcceleratorResponse> {
  const res = await apiFetch(`${API_BASE}/accelerators/sessions/${sessionId}`, {
    cache: "no-store",
  });
  return res.json();
}

export async function postAcceleratorMessage(
  sessionId: string,
  content: string,
): Promise<AcceleratorMessage> {
  const res = await apiFetch(`${API_BASE}/accelerators/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  return res.json();
}

export interface PromoteAcceleratorPayload {
  project_id?: string;
  name?: string;
  description?: string;
}

export interface PromoteAcceleratorResponse {
  session: AcceleratorSession;
  project_id: string;
}

export async function promoteAcceleratorSession(
  sessionId: string,
  payload: PromoteAcceleratorPayload,
): Promise<PromoteAcceleratorResponse> {
  const res = await apiFetch(`${API_BASE}/accelerators/sessions/${sessionId}/promote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function listCatalogIntents(
  persona?: string,
  options?: { forceRefresh?: boolean },
): Promise<CatalogIntent[]> {
  const key = (persona || "__default__").toLowerCase();
  const entry = catalogCache.get(key);
  const now = Date.now();
  const expired = !entry || now - entry.fetchedAt > CATALOG_CACHE_TTL_MS;

  if (!options?.forceRefresh && entry && !expired) {
    return entry.data;
  }

  if (!options?.forceRefresh) {
    const pending = catalogPending.get(key);
    if (pending) return pending;
  }

  const query = persona ? `?persona=${encodeURIComponent(persona)}` : "";
  const fetchPromise = (async () => {
    const res = await apiFetch(`${API_BASE}/catalog/intents${query}`, {
      cache: "no-store",
    });
    const data: CatalogIntent[] = await res.json();
    catalogCache.set(key, { data, fetchedAt: Date.now() });
    return data;
  })();

  catalogPending.set(key, fetchPromise);
  try {
    return await fetchPromise;
  } finally {
    catalogPending.delete(key);
  }
}

export async function analyzeUploads(
  project_id: string,
  files: File[],
): Promise<UploadAnalyzeResponse> {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  const res = await apiFetch(
    `${API_BASE}/projects/${encodeURIComponent(project_id)}/uploads/analyze`,
    {
      method: "POST",
      body: fd,
    } as any,
  );
  return res.json();
}

export async function applyUploadRequirements(
  project_id: string,
  req: UploadApplyRequest,
): Promise<ProjectContext> {
  const res = await apiFetch(
    `${API_BASE}/projects/${encodeURIComponent(project_id)}/uploads/apply`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req || {}),
    },
  );
  return res.json();
}

// --- Telemetry (client-side only) ---
export type TelemetryEvent = {
  name: string;
  properties?: Record<string, any>;
};

type TelemetrySink = (event: TelemetryEvent) => void;

const telemetryListeners: TelemetrySink[] = [];
const telemetryBuffer: TelemetryEvent[] = [];
const TELEMETRY_BATCH_SIZE = 12;
const TELEMETRY_FLUSH_INTERVAL_MS = 5000;
let telemetryFlushTimer: number | null = null;
let telemetrySinkRegistered = false;

export function addTelemetryListener(listener: TelemetrySink) {
  telemetryListeners.push(listener);
}

export function trackEvent(name: string, properties?: Record<string, any>) {
  const payload = { name, properties: properties ?? {} };
  if (typeof window !== "undefined" && (window as any).analytics?.track) {
    try {
      (window as any).analytics.track(name, properties ?? {});
    } catch {
      // fallthrough to local listeners
    }
  }
  telemetryListeners.forEach((listener) => {
    try {
      listener(payload);
    } catch {
      // ignore listener failures
    }
  });
}

function enqueueTelemetry(event: TelemetryEvent) {
  telemetryBuffer.push(event);
  if (telemetryBuffer.length >= TELEMETRY_BATCH_SIZE) {
    void flushTelemetryBuffer(true);
    return;
  }
  if (typeof window !== "undefined") {
    if (telemetryFlushTimer !== null) {
      window.clearTimeout(telemetryFlushTimer);
    }
    telemetryFlushTimer = window.setTimeout(() => {
      telemetryFlushTimer = null;
      void flushTelemetryBuffer();
    }, TELEMETRY_FLUSH_INTERVAL_MS);
  }
}

async function flushTelemetryBuffer(forceImmediate = false) {
  if (!telemetryBuffer.length) return;
  const events = telemetryBuffer.splice(0, telemetryBuffer.length);
  const payload = {
    source: TELEMETRY_SOURCE,
    events: events.map((event) => ({ name: event.name, properties: event.properties ?? {} })),
  };

  try {
    if (
      !forceImmediate &&
      typeof navigator !== "undefined" &&
      typeof navigator.sendBeacon === "function"
    ) {
      const blob = new Blob([JSON.stringify(payload)], {
        type: "application/json",
      });
      if (navigator.sendBeacon(TELEMETRY_ENDPOINT, blob)) {
        return;
      }
    }

    await apiFetch(TELEMETRY_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    // Swallow errors; telemetry should never block UX.
  }
}

function ensureTelemetrySink() {
  if (telemetrySinkRegistered) return;
  if (typeof window === "undefined") return;
  telemetrySinkRegistered = true;
  addTelemetryListener(enqueueTelemetry);
  window.addEventListener("beforeunload", () => {
    void flushTelemetryBuffer(true);
  });
}

if (typeof window !== "undefined") {
  ensureTelemetrySink();
}

function getStoredPersonaOverride(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const override = window.localStorage.getItem("opnxt_persona_override");
    return override || null;
  } catch {
    return null;
  }
}

type PersonaHints = {
  email?: string | null;
};

export function derivePersonaFromRoles(
  roles?: string[],
  hints?: PersonaHints,
): string | null {
  const stored = getStoredPersonaOverride();
  if (stored) return stored.toLowerCase();

  const normalized = (roles || []).map((role) => role.toLowerCase());

  const heuristics: Array<{ match: RegExp; persona: string }> = [
    { match: /(architect|admin|platform|systems?)/, persona: "architect" },
    { match: /(approver|govern|compliance|review)/, persona: "approver" },
    { match: /(engineer|developer|dev|qa|quality|tester|sdet|contributor)/, persona: "engineer" },
    { match: /(analyst|research|insight|data)/, persona: "analyst" },
    { match: /(auditor|risk|security)/, persona: "auditor" },
    { match: /(product|project|manager|pm|lead)/, persona: "pm" },
  ];

  for (const role of normalized) {
    for (const rule of heuristics) {
      if (rule.match.test(role)) {
        return rule.persona;
      }
    }
  }

  if (hints?.email) {
    const email = hints.email.toLowerCase();
    if (email.includes("qa") || email.includes("dev") || email.includes("eng")) return "engineer";
    if (email.includes("product") || email.includes("pm")) return "pm";
  }

  if (normalized.length > 0) {
    return normalized[0];
  }

  return null;
}
