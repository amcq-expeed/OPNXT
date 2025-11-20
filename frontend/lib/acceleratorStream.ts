export type ProgressUpdate = {
  id: string;
  message: string;
  kind: "info" | "success" | "error";
  timestamp: number;
  stage?: string | null;
  progress?: number | null;
};

function parseStreamTimestamp(value: any): number | null {
  if (!value) return null;
  const text = typeof value === "string" ? value : typeof value === "number" ? value : null;
  if (text == null) return null;
  const date = new Date(text);
  const time = date.getTime();
  return Number.isNaN(time) ? null : time;
}

export const PROGRESS_STAGE_LABELS: Record<string, string> = {
  analysis: "Collecting context",
  draft: "Drafting deliverables",
  edit: "Applying edits",
  validation: "Validating outputs",
  ready: "Ready",
  packaging: "Packaging deliverables",
};

export const PROGRESS_STAGE_ORDER = ["analysis", "draft", "edit", "validation", "packaging", "ready"] as const;

export function formatBadgeLabel(value: string | null | undefined): string | null {
  if (!value) return null;
  const normalized = value.replace(/[_-]+/g, " ").trim();
  if (!normalized) return null;
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

export function formatProgressStage(stage?: string | null): string | null {
  if (!stage) return null;
  const key = stage.toLowerCase();
  if (PROGRESS_STAGE_LABELS[key]) return PROGRESS_STAGE_LABELS[key];
  return formatBadgeLabel(stage);
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  const rounded = Math.round(value);
  if (rounded < 0) return 0;
  if (rounded > 100) return 100;
  return rounded;
}

export function convertProgressToPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value <= 1) {
    return clampPercent(Math.round(value * 100));
  }
  return clampPercent(Math.round(value));
}

export function extractStage(payload: any): string | null {
  if (!payload) return null;
  if (typeof payload?.stage === "string" && payload.stage.trim()) return payload.stage.trim();
  if (typeof payload?.meta?.stage === "string" && payload.meta.stage.trim()) return payload.meta.stage.trim();
  return null;
}

export function extractProgressValue(payload: any): number | null {
  if (!payload) return null;
  const value =
    typeof payload?.progress === "number" && Number.isFinite(payload.progress)
      ? payload.progress
      : typeof payload?.meta?.progress === "number" && Number.isFinite(payload.meta.progress)
        ? payload.meta.progress
        : null;
  if (value == null) return null;
  return value;
}

export type StageTimelineItem = {
  stage: string;
  label: string;
  state: "done" | "active" | "pending";
};

export function buildStageTimeline(
  updates: ProgressUpdate[],
  latestStage: string | null | undefined,
): StageTimelineItem[] {
  if (!updates.length) return [];

  const seenStages: string[] = [];
  updates.forEach((update) => {
    const stage =
      typeof update.stage === "string" && update.stage.trim() ? update.stage.trim().toLowerCase() : null;
    if (!stage) return;
    if (!seenStages.includes(stage)) {
      seenStages.push(stage);
    }
  });

  const normalizedActiveStage =
    typeof latestStage === "string" && latestStage.trim() ? latestStage.trim().toLowerCase() : null;
  const orderedStages: string[] = [];

  PROGRESS_STAGE_ORDER.forEach((stage) => {
    if (seenStages.includes(stage) || stage === normalizedActiveStage) {
      orderedStages.push(stage);
    }
  });

  seenStages.forEach((stage) => {
    if (!orderedStages.includes(stage)) {
      orderedStages.push(stage);
    }
  });

  if (normalizedActiveStage && !orderedStages.includes(normalizedActiveStage)) {
    orderedStages.push(normalizedActiveStage);
  }

  if (!orderedStages.length) return [];

  const activeIndex = normalizedActiveStage ? orderedStages.indexOf(normalizedActiveStage) : orderedStages.length - 1;
  const seenStageSet = new Set(seenStages);

  return orderedStages.map((stage, index) => {
    const label = formatProgressStage(stage) ?? formatBadgeLabel(stage) ?? stage;
    let state: "done" | "active" | "pending" = "pending";

    if (normalizedActiveStage) {
      if (stage === normalizedActiveStage) state = "active";
      else if (activeIndex !== -1 && index < activeIndex) state = "done";
      else if (seenStageSet.has(stage) && index < orderedStages.length - 1) state = "done";
    } else if (seenStageSet.has(stage)) {
      state = index === orderedStages.length - 1 ? "active" : "done";
    }

    return {
      stage,
      label,
      state,
    };
  });
}

export type ProgressEntryInstruction = {
  message: string;
  kind: ProgressUpdate["kind"];
  stage?: string | null;
  progress?: number | null;
  timestamp?: number | null;
};

export type StreamUpdateInterpretation = {
  progressEntries: ProgressEntryInstruction[];
  streamError?: string | null;
  actionStatus?: string | null;
  nextLiveDraft?: string | null;
  clearLiveDraft?: boolean;
  openDrawer?: boolean;
  activateStream?: boolean;
  stopStream?: boolean;
};

export function interpretStreamUpdates(updates: any[]): StreamUpdateInterpretation {
  const interpretation: StreamUpdateInterpretation = {
    progressEntries: [],
  };

  if (!Array.isArray(updates) || updates.length === 0) {
    return interpretation;
  }

  updates.forEach((update) => {
    if (!update) return;
    const stage = extractStage(update);
    const progressValue = extractProgressValue(update);
    const previewText = typeof update?.preview === "string" ? update.preview : null;
    const type = typeof update?.type === "string" ? update.type.toLowerCase() : "";
    const timestamp =
      parseStreamTimestamp(update?.ts) ??
      parseStreamTimestamp(update?.meta?.ts) ??
      parseStreamTimestamp(update?.meta?.timestamp);

    if (type && type !== "draft_update") {
      interpretation.openDrawer = true;
    }

    switch (type) {
      case "error":
        if (previewText) {
          interpretation.streamError = previewText;
          interpretation.progressEntries.push({
            message: previewText,
            kind: "error",
            stage: stage ?? "error",
            progress: progressValue ?? null,
            timestamp,
          });
        }
        break;
      case "status":
        if (previewText) {
          interpretation.actionStatus = previewText;
          interpretation.progressEntries.push({
            message: previewText,
            kind: "info",
            stage,
            progress: progressValue ?? null,
            timestamp,
          });
          interpretation.activateStream = true;
          if (stage && stage.toLowerCase() !== "draft") {
            interpretation.openDrawer = true;
          }
        }
        break;
      case "draft_update":
        if (previewText) {
          interpretation.nextLiveDraft = previewText;
          interpretation.progressEntries.push({
            message: "Drafting artifacts…",
            kind: "info",
            stage: stage ?? "draft",
            progress: progressValue ?? 0.45,
            timestamp,
          });
          interpretation.activateStream = true;
          interpretation.openDrawer = true;
        }
        break;
      case "commit":
        if (previewText) {
          interpretation.progressEntries.push({
            message: previewText,
            kind: "success",
            stage: stage ?? "ready",
            progress: progressValue ?? 1,
            timestamp,
          });
          interpretation.activateStream = true;
          interpretation.stopStream = true;
          interpretation.clearLiveDraft = true;
          interpretation.openDrawer = true;
        }
        break;
      default:
        if (previewText) {
          interpretation.progressEntries.push({
            message: previewText,
            kind: "info",
            stage,
            progress: progressValue ?? null,
            timestamp,
          });
        }
        break;
    }
  });

  return interpretation;
}
