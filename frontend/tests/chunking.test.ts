import assert from "node:assert/strict";
import test from "node:test";

import { isSentryModule } from "../build/chunking.ts";


test("matches only @sentry modules for the dedicated vendor group", () => {
  assert.equal(
    isSentryModule("/workspace/frontend/node_modules/@sentry/react/build/npm/esm/index.js"),
    true,
  );
  assert.equal(
    isSentryModule("C:\\workspace\\frontend\\node_modules\\@sentry\\core\\build\\index.js"),
    true,
  );
});


test("does not capture application or unrelated dependency modules", () => {
  assert.equal(isSentryModule("/workspace/frontend/src/main.tsx"), false);
  assert.equal(
    isSentryModule("/workspace/frontend/node_modules/react/index.js"),
    false,
  );
});
