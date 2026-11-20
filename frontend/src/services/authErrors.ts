/** A stable, provider-free error code suitable for UI translation. */
export class AuthError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.name = "AuthError";
    this.code = code;
  }
}


export function authErrorCode(error: unknown): string {
  return error instanceof AuthError ? error.code : "AUTH_REQUEST_FAILED";
}


/**
 * Normalizes provider responses before they cross into UI code. The message is
 * examined only for Cognito's already-confirmed state and is never retained or
 * rendered to a merchant.
 */
export function cognitoErrorCode(data: Record<string, unknown>): string {
  const raw = data.__type || data.code || data.Code;
  const code = typeof raw === "string"
    ? raw.split("#").pop() || "AUTH_REQUEST_FAILED"
    : "AUTH_REQUEST_FAILED";
  const message = typeof data.message === "string"
    ? data.message
    : typeof data.Message === "string"
      ? data.Message
      : "";

  if (
    code === "NotAuthorizedException"
    && /(?:current status is confirmed|already confirmed)/i.test(message)
  ) {
    return "USER_ALREADY_CONFIRMED";
  }

  return code;
}
