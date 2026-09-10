import { describe, expect, it } from "vitest";

import { getPaddleInitializationOptions } from "../src/config/paddle";

describe("Paddle runtime configuration", () => {
  it("infers sandbox from test tokens", () => {
    expect(getPaddleInitializationOptions(undefined, "test_abc")).toEqual({
      token: "test_abc",
      environment: "sandbox",
    });
  });

  it("infers live mode from live tokens and omits sandbox environment", () => {
    expect(getPaddleInitializationOptions(undefined, "live_abc")).toEqual({
      token: "live_abc",
    });
  });

  it("rejects a sandbox token in production", () => {
    expect(() =>
      getPaddleInitializationOptions("production", "test_abc"),
    ).toThrow("Production Paddle environment requires a live_ client-side token");
  });

  it("rejects a live token in sandbox", () => {
    expect(() =>
      getPaddleInitializationOptions("sandbox", "live_abc"),
    ).toThrow("Sandbox Paddle environment requires a test_ client-side token");
  });

  it("rejects missing tokens", () => {
    expect(() => getPaddleInitializationOptions("sandbox", undefined)).toThrow(
      "VITE_PADDLE_CLIENT_TOKEN is not configured",
    );
  });

  it("rejects unknown environments", () => {
    expect(() => getPaddleInitializationOptions("staging", "test_abc")).toThrow(
      "VITE_PADDLE_ENVIRONMENT must be 'sandbox' or 'production'",
    );
  });
});
