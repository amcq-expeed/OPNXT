const MODEL_PREF_KEY = "opnxt_chat_model_preference";

export type ModelPreference = {
  provider: string;
  model: string;
};

export function getModelPreference(): ModelPreference | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(MODEL_PREF_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (typeof parsed?.provider === "string" && typeof parsed?.model === "string") {
      return { provider: parsed.provider, model: parsed.model };
    }
  } catch {}
  return null;
}

export function setModelPreference(provider: string, model: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      MODEL_PREF_KEY,
      JSON.stringify({ provider, model }),
    );
  } catch {}
}
