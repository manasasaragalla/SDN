import assert from "node:assert/strict";
import test from "node:test";

import {
  activeTopologyLabel,
  activateVersionRequest,
  canActivateTopology,
  isHistoricalVersion,
} from "../src/lib/topology-version-controls.ts";

test("historical versions remain read-only but can be activated when inactive", () => {
  const versionOneIsHistorical = isHistoricalVersion(1, 2);
  assert.equal(versionOneIsHistorical, true);
  assert.equal(canActivateTopology(true, false, false, true), true);
  assert.equal(canActivateTopology(true, false, true, true), false);
});

test("activation request names the exact selected version", () => {
  assert.deepEqual(activateVersionRequest(1), {
    method: "POST",
    body: "{\"version\":1}",
  });
});

test("active indicator reports the pointer version independently of the editor version", () => {
  const activeVersion = { name: "test1", version: 1 };
  const editorVersion = 2;

  assert.equal(activeTopologyLabel(activeVersion), "Active planning topology · test1 · v1");
  assert.notEqual(activeVersion.version, editorVersion);
});
