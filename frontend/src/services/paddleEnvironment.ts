/**
 * Paddle.js has separate sandbox and production workspaces.
 *
 * A test_ token is only usable in sandbox; a live_ token is only usable
 * in production. Never infer commercial go-live solely from a token:
 * production mode requires an explicit build-time opt-in as well.
 *
 * No keys, tokens or checkout payloads are logged.
 */
export type PaddleJsEnvironment = "sandbox" | "production";

const TOKEN_FORMAT = /^(test|live)_[a-zA-Z0-9]{27}$/;

export function resolvePaddleJsEnvironment(
  clientToken: unknown,
  configuredEnvironment: unknown,
): PaddleJsEnvironment | null {
  if (typeof clientToken !== "string" || !TOKEN_FORMAT.test(clientToken.trim())) {
    return null;
  }
  const environment =
    configuredEnvironment == null || configuredEnvironment === ""
      ? "sandbox"
      : configuredEnvironment;
  if (environment !== "sandbox" && environment !== "production") {
    return null;
  }
  const token = clientToken.trim();
  if (environment === "sandbox" && token.startsWith("test_")) return "sandbox";
  if (environment === "production" && token.startsWith("live_")) return "production";
  return null;
}
