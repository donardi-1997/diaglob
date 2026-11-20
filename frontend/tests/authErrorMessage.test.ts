import assert from "node:assert/strict";
import test from "node:test";

import { AuthError, cognitoErrorCode } from "../src/services/authErrors.ts";
import { authErrorMessageKey, isAlreadyConfirmed } from "../src/services/authErrorMessage.ts";


test("Cognito errors map to translated UI keys, never provider text", () => {
  assert.equal(
    authErrorMessageKey(new AuthError("NotAuthorizedException"), "loginI18nLoginError"),
    "loginI18nInvalidCredentials",
  );
  assert.equal(
    authErrorMessageKey(new AuthError("InvalidPasswordException"), "loginI18nCreateError"),
    "loginI18nPasswordPolicyError",
  );
  assert.equal(
    authErrorMessageKey(new AuthError("CodeMismatchException"), "loginI18nConfirmError"),
    "loginI18nInvalidCode",
  );
  assert.equal(
    authErrorMessageKey(new Error("Cognito said: internal details"), "loginI18nLoginError"),
    "loginI18nLoginError",
  );
});


test("only Cognito's already-confirmed control code is accepted", () => {
  assert.equal(
    cognitoErrorCode({
      __type: "NotAuthorizedException",
      message: "User cannot be confirmed. Current status is CONFIRMED",
    }),
    "USER_ALREADY_CONFIRMED",
  );
  assert.equal(isAlreadyConfirmed(new AuthError("USER_ALREADY_CONFIRMED")), true);
  assert.equal(isAlreadyConfirmed(new AuthError("NotAuthorizedException")), false);
  assert.equal(isAlreadyConfirmed(new AuthError("CodeMismatchException")), false);
  assert.equal(isAlreadyConfirmed(new Error("already confirmed")), false);
});
