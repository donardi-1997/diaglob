import assert from "node:assert/strict";
import test from "node:test";

import { validateAgentStoreAssignment } from "../src/services/agentEditorValidation.ts";

test("active AI agents require an authorized active store", () => {
  assert.equal(validateAgentStoreAssignment(true, [], [11]), "STORE_REQUIRED");
  assert.equal(validateAgentStoreAssignment(true, [11], [11]), null);
  assert.equal(validateAgentStoreAssignment(true, [11, 12], [11, 12]), null);
});
test("reject stale, deleted, inactive or cross-tenant store assignments", () => {
  assert.equal(validateAgentStoreAssignment(true, [12], [11]), "STORE_UNAVAILABLE");
  assert.equal(validateAgentStoreAssignment(false, [12], [11]), "STORE_UNAVAILABLE");
  assert.equal(validateAgentStoreAssignment(true, [0], [11]), "STORE_UNAVAILABLE");
  assert.equal(validateAgentStoreAssignment(true, [11.5], [11]), "STORE_UNAVAILABLE");
});
test("inactive drafts may have no store assignment", () => {
  assert.equal(validateAgentStoreAssignment(false, [], [11]), null);
  assert.equal(validateAgentStoreAssignment(false, [], []), null);
});
