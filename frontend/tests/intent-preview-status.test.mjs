import assert from "node:assert/strict";
import test from "node:test";

import { deriveIntentPreviewStatuses } from "../src/lib/intent-preview-status.mjs";

test("selected DESIGN candidate keeps interpretation, planning, and execution separate", () => {
  const backendPreview = {
    interpretation_status: "VALID",
    capability_resolution: { eligibility: "CAPABILITY_READY" },
    planning_eligible: true,
    planning_result: { status: "SELECTED" },
    execution_status: "UNAVAILABLE",
    execution_eligible: false,
    topology_identity: { mode: "DESIGN" },
  };

  assert.deepEqual(
    deriveIntentPreviewStatuses(backendPreview).map(({ label }) => label),
    [
      "Intent interpretation: Valid",
      "Planning: Eligible candidate selected",
      "Execution: Unavailable — DESIGN topology",
    ],
  );
});

test("no eligible planning candidate does not change unavailable execution", () => {
  const statuses = deriveIntentPreviewStatuses({
    interpretation_status: "VALID",
    planning_eligible: false,
    planning_result: { status: "NO_ELIGIBLE_PATH" },
    execution_status: "UNAVAILABLE",
    topology_identity: { mode: "DESIGN" },
  });

  assert.equal(statuses[1].label, "Planning: No eligible candidate");
  assert.equal(statuses[2].label, "Execution: Unavailable — DESIGN topology");
});
