import assert from "node:assert/strict";
import test from "node:test";

import { formatApiErrorDetail } from "../src/lib/api-error-detail.mjs";

test("structured FastAPI validation details produce readable API errors", () => {
  const detail = formatApiErrorDetail([{
    type: "value_error",
    loc: ["body", "graph", "links", 0, "port_a"],
    msg: "Value error, Switch port s1:2 is assigned more than once.",
  }]);

  assert.equal(
    detail,
    "graph.links[0].port_a: Value error, Switch port s1:2 is assigned more than once.",
  );
});

test("string API details, including version conflicts, are preserved", () => {
  const detail = "Topology changed: expected version 1, current version is 2.";
  assert.equal(formatApiErrorDetail(detail), detail);
});
