import type { IntentPreviewResponse } from "@/types/api";

export interface StoredPlanningPreview {
  naturalLanguage: string;
  savedAt: string;
  response: IntentPreviewResponse;
}

export function savePlanningPreview(
  naturalLanguage: string,
  response: IntentPreviewResponse,
): boolean;
export function clearPlanningPreview(): void;
export function getPlanningPreviewSnapshot(): StoredPlanningPreview | null;
export function subscribePlanningPreview(onChange: () => void): () => void;
