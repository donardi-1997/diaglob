import assert from "node:assert/strict";
import test from "node:test";

import { initializeFrontendObservability } from "../src/observability.ts";


test("does not initialize Sentry when the DSN is empty", () => {
  let calls = 0;

  const enabled = initializeFrontendObservability(
    {
      VITE_SENTRY_DSN: "",
      VITE_SENTRY_ENVIRONMENT: "production",
      VITE_SENTRY_RELEASE: "diaglob@test",
      VITE_SENTRY_TRACES_SAMPLE_RATE: "0.05",
    },
    () => {
      calls += 1;
    },
  );

  assert.equal(enabled, false);
  assert.equal(calls, 0);
});


test("initializes Sentry with privacy-safe production options", () => {
  let received: Record<string, unknown> | undefined;

  const enabled = initializeFrontendObservability(
    {
      VITE_SENTRY_DSN: "https://public@example.ingest.sentry.io/123",
      VITE_SENTRY_ENVIRONMENT: "production",
      VITE_SENTRY_RELEASE: "diaglob@abc1234",
      VITE_SENTRY_TRACES_SAMPLE_RATE: "0.05",
    },
    (options) => {
      received = options;
    },
  );

  assert.equal(enabled, true);
  assert.deepEqual(received, {
    dsn: "https://public@example.ingest.sentry.io/123",
    environment: "production",
    release: "diaglob@abc1234",
    tracesSampleRate: 0.05,
    sendDefaultPii: false,
  });
});


test("uses a zero trace sample rate when the configured value is invalid", () => {
  let received: Record<string, unknown> | undefined;

  initializeFrontendObservability(
    {
      VITE_SENTRY_DSN: "https://public@example.ingest.sentry.io/123",
      VITE_SENTRY_TRACES_SAMPLE_RATE: "2",
    },
    (options) => {
      received = options;
    },
  );

  assert.equal(received?.tracesSampleRate, 0);
});
