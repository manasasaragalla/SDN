export function deriveIntentPreviewStatuses(preview) {
  const planning = preview.planning_eligible === true
    ? "Eligible candidate selected"
    : preview.planning_eligible === false
      ? "No eligible candidate"
      : "Not assessed";
  const execution = preview.execution_status === "AVAILABLE"
    ? "Available"
    : preview.topology_identity?.mode === "DESIGN"
      ? "Unavailable — DESIGN topology"
      : "Unavailable";

  return [
    {
      label: `Intent interpretation: ${preview.interpretation_status === "VALID" ? "Valid" : "Clarification required"}`,
      tone: preview.interpretation_status === "VALID" ? "positive" : "warning",
    },
    {
      label: `Planning: ${planning}`,
      tone: preview.planning_eligible === true
        ? "positive"
        : preview.planning_eligible === false
          ? "negative"
          : "warning",
    },
    {
      label: `Execution: ${execution}`,
      tone: preview.execution_status === "AVAILABLE" ? "positive" : "neutral",
    },
  ];
}
