export const ACCELERATOR_SESSION_STORAGE_KEY = "opnxt-accelerator-sessions";

function readRawSessionMap(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const payload = window.localStorage.getItem(ACCELERATOR_SESSION_STORAGE_KEY);
    if (!payload) return {};
    const parsed = JSON.parse(payload);
    if (parsed && typeof parsed === "object") {
      return parsed as Record<string, string>;
    }
    return {};
  } catch (error) {
    console.error("accelerator_session_store_read_failed", error);
    return {};
  }
}

function writeRawSessionMap(next: Record<string, string>): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(ACCELERATOR_SESSION_STORAGE_KEY, JSON.stringify(next));
  } catch (error) {
    console.error("accelerator_session_store_write_failed", error);
  }
}

export function getStoredAcceleratorSessions(): Record<string, string> | null {
  if (typeof window === "undefined") return null;
  return readRawSessionMap();
}

export function getStoredAcceleratorSession(intentId: string | null | undefined): string | null {
  if (!intentId) return null;
  const sessions = getStoredAcceleratorSessions();
  if (!sessions) return null;
  return typeof sessions[intentId] === "string" ? sessions[intentId] : null;
}

export function setStoredAcceleratorSession(intentId: string, sessionId: string): void {
  if (!intentId || !sessionId || typeof window === "undefined") return;
  const current = readRawSessionMap();
  current[intentId] = sessionId;
  writeRawSessionMap(current);
}

export function removeStoredAcceleratorSession(intentId?: string): void {
  if (typeof window === "undefined") return;
  if (!intentId) {
    writeRawSessionMap({});
    return;
  }
  const current = readRawSessionMap();
  if (current[intentId]) {
    delete current[intentId];
    writeRawSessionMap(current);
  }
}
