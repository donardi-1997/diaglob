import assert from "node:assert/strict";
import test from "node:test";

import { manualVendorChunk } from "../build/chunking.ts";


test("isolates Sentry into its own vendor chunk", () => {
  assert.equal(
    manualVendorChunk("/workspace/frontend/node_modules/@sentry/react/build/npm/esm/index.js"),
    "sentry-vendor",
  );
});


test("leaves application and unrelated dependencies to Vite", () => {
  assert.equal(manualVendorChunk("/workspace/frontend/src/main.tsx"), undefined);
  assert.equal(
    manualVendorChunk("/workspace/frontend/node_modules/react/index.js"),
    undefined,
  );
});
