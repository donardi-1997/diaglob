import assert from "node:assert/strict";
import test from "node:test";

import { getAnalyticsRangeDates } from "../src/utils/analyticsDateRange.ts";


const now = new Date(2026, 8, 10, 23, 30, 0);


test("today uses the current local calendar date", () => {
  assert.deepEqual(getAnalyticsRangeDates("today", now), {
    from: "2026-09-10",
    to: "2026-09-10",
  });
});


test("7d is exactly seven inclusive calendar days", () => {
  assert.deepEqual(getAnalyticsRangeDates("7d", now), {
    from: "2026-09-04",
    to: "2026-09-10",
  });
});


test("30d is exactly thirty inclusive calendar days", () => {
  assert.deepEqual(getAnalyticsRangeDates("30d", now), {
    from: "2026-08-12",
    to: "2026-09-10",
  });
});


test("month starts on the first local calendar day", () => {
  assert.deepEqual(getAnalyticsRangeDates("month", now), {
    from: "2026-09-01",
    to: "2026-09-10",
  });
});


test("calendar subtraction crosses year boundaries correctly", () => {
  const january = new Date(2026, 0, 3, 12, 0, 0);
  assert.deepEqual(getAnalyticsRangeDates("7d", january), {
    from: "2025-12-28",
    to: "2026-01-03",
  });
});


test("all time returns no date bounds", () => {
  assert.deepEqual(getAnalyticsRangeDates("", now), {
    from: "",
    to: "",
  });
});
