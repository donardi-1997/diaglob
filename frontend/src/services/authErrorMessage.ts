import { authErrorCode } from "./authErrors.ts";

/**
 * Maps Cognito/internal codes to i18n keys. Never return provider text:
 * Cognito messages are English and may reveal account state or policy detail.
 */
export function authErrorMessageKey(error: unknown, fallback: string): string {
  switch (authErrorCode(error)) {
    case "NotAuthorizedException":
    case "UserNotFoundException":
      return "loginI18nInvalidCredentials";
    case "UserNotConfirmedException":
      return "loginI18nConfirmationRequired";
    case "UsernameExistsException":
      return "loginI18nEmailAlreadyRegistered";
    case "InvalidPasswordException":
      return "loginI18nPasswordPolicyError";
    case "CodeMismatchException":
      return "loginI18nInvalidCode";
    case "ExpiredCodeException":
      return "loginI18nExpiredCode";
    case "LimitExceededException":
    case "TooManyRequestsException":
      return "loginI18nTryLater";
    case "ACCOUNT_PROVISION_FAILED":
      return "loginI18nProvisionError";
    default:
      return fallback;
  }
}


export function isAlreadyConfirmed(error: unknown): boolean {
  return authErrorCode(error) === "USER_ALREADY_CONFIRMED";
}
