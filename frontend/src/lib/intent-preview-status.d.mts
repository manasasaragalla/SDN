export type IntentPreviewStatusInput = {
  interpretation_status: "VALID" | "CLARIFICATION_REQUIRED";
  planning_eligible: boolean | null;
  planning_result: { status: string } | null;
  execution_status: "AVAILABLE" | "UNAVAILABLE";
  topology_identity: { mode: "DESIGN" | "MININET" | "LIVE" } | null;
};

export function deriveIntentPreviewStatuses(
  preview: IntentPreviewStatusInput,
): {
  label: string;
  tone: "positive" | "warning" | "negative" | "neutral";
}[];
