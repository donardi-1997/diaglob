import {
  COGNITO_CLIENT_ID,
  COGNITO_ENDPOINT,
} from "./config";

export interface CognitoAuthenticationResult {
  AccessToken: string;
  IdToken: string;
  RefreshToken?: string;
  ExpiresIn: number;
  TokenType: string;
}

interface CognitoAuthResponse {
  AuthenticationResult?: CognitoAuthenticationResult;
  ChallengeName?: string;
}

async function cognitoRequest(
  target: string,
  body: Record<string, unknown>,
) {
  const response = await fetch(COGNITO_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target":
        `AWSCognitoIdentityProviderService.${target}`,
    },
    body: JSON.stringify(body),
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(
      data.message ||
      data.Message ||
      "No fue posible autenticar la cuenta.",
    );
  }

  return data;
}

export async function login(
  email: string,
  password: string,
) {
  const data = (await cognitoRequest("InitiateAuth", {
    AuthFlow: "USER_PASSWORD_AUTH",
    ClientId: COGNITO_CLIENT_ID,
    AuthParameters: {
      USERNAME: email.trim(),
      PASSWORD: password,
    },
  })) as CognitoAuthResponse;

  if (!data.AuthenticationResult) {
    throw new Error(
      data.ChallengeName
        ? `La cuenta requiere completar: ${data.ChallengeName}`
        : "Cognito no devolvió una sesión válida.",
    );
  }

  return data.AuthenticationResult;
}

export async function refreshSession(
  refreshToken: string,
) {
  const data = (await cognitoRequest("InitiateAuth", {
    AuthFlow: "REFRESH_TOKEN_AUTH",
    ClientId: COGNITO_CLIENT_ID,
    AuthParameters: {
      REFRESH_TOKEN: refreshToken,
    },
  })) as CognitoAuthResponse;

  if (!data.AuthenticationResult) {
    throw new Error("No fue posible renovar la sesión.");
  }

  return data.AuthenticationResult;
}
