export type PaddleEnvironment = "sandbox" | "production";

export type PaddleInitializationOptions =
  | { token: string; environment: "sandbox" }
  | { token: string };

function inferEnvironmentFromToken(token: string): PaddleEnvironment | null {
  if (token.startsWith("test_")) {
    return "sandbox";
  }

  if (token.startsWith("live_")) {
    return "production";
  }

  return null;
}

export function getPaddleInitializationOptions(
  rawEnvironment: string | undefined,
  rawToken: string | undefined,
): PaddleInitializationOptions {
  const token = rawToken?.trim() || "";

  if (!token) {
    throw new Error("VITE_PADDLE_CLIENT_TOKEN is not configured");
  }

  const configuredEnvironment = rawEnvironment?.trim().toLowerCase() || "";
  const inferredEnvironment = inferEnvironmentFromToken(token);

  if (configuredEnvironment && !["sandbox", "production"].includes(configuredEnvironment)) {
    throw new Error(
      "VITE_PADDLE_ENVIRONMENT must be 'sandbox' or 'production'",
    );
  }

  const environment = (configuredEnvironment || inferredEnvironment) as PaddleEnvironment | null;

  if (!environment) {
    throw new Error(
      "Unable to infer Paddle environment: client-side token must start with test_ or live_",
    );
  }

  if (environment === "sandbox" && !token.startsWith("test_")) {
    throw new Error("Sandbox Paddle environment requires a test_ client-side token");
  }

  if (environment === "production" && !token.startsWith("live_")) {
    throw new Error("Production Paddle environment requires a live_ client-side token");
  }

  if (environment === "sandbox") {
    return { token, environment: "sandbox" };
  }

  // Paddle.js defaults to live when no sandbox environment is supplied.
  return { token };
}
