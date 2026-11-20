import { AuthError, authErrorCode, cognitoErrorCode } from "./authErrors";

const REGION =
  import.meta.env.VITE_AWS_REGION ||
  "us-east-2";

const CLIENT_ID =
  import.meta.env.VITE_COGNITO_CLIENT_ID ||
  "7gas2mvvovukjpk05jhbku4303";

const COGNITO_ENDPOINT =
  `https://cognito-idp.${REGION}.amazonaws.com/`;


interface CognitoAuthenticationResult {
  AccessToken: string;
  IdToken: string;
  RefreshToken?: string;
  ExpiresIn: number;
  TokenType: string;
}


interface CognitoAuthResponse {
  AuthenticationResult?:
    CognitoAuthenticationResult;

  ChallengeName?: string;
}


export { AuthError, authErrorCode };


async function cognitoRequest(
  target: string,
  body: Record<string, unknown>,
) {
  const response = await fetch(
    COGNITO_ENDPOINT,
    {
      method: "POST",

      headers: {
        "Content-Type":
          "application/x-amz-json-1.1",

        "X-Amz-Target":
          `AWSCognitoIdentityProviderService.${target}`,
      },

      body:
        JSON.stringify(body),
    },
  );

  let data: Record<string, unknown> = {};
  try {
    data = await response.json();
  } catch {
    // Do not expose an upstream HTML/proxy body to the login screen.
  }

  if (!response.ok) {
    throw new AuthError(cognitoErrorCode(data));
  }

  return data;
}


export async function login(
  email: string,
  password: string,
) {
  const data =
    (await cognitoRequest(
      "InitiateAuth",
      {
        AuthFlow:
          "USER_PASSWORD_AUTH",

        ClientId:
          CLIENT_ID,

        AuthParameters: {
          USERNAME: email,
          PASSWORD: password,
        },
      },
    )) as CognitoAuthResponse;

  if (!data.AuthenticationResult) {
    throw new AuthError("AUTH_TOKENS_MISSING");
  }

  return data.AuthenticationResult;
}


export async function signUp(
  name: string,
  email: string,
  password: string,
) {
  return cognitoRequest(
    "SignUp",
    {
      ClientId:
        CLIENT_ID,

      Username:
        email,

      Password:
        password,

      UserAttributes: [
        {
          Name: "email",
          Value: email,
        },
        {
          Name: "name",
          Value: name,
        },
      ],
    },
  );
}


export async function confirmSignUp(
  email: string,
  code: string,
) {
  return cognitoRequest(
    "ConfirmSignUp",
    {
      ClientId:
        CLIENT_ID,

      Username:
        email,

      ConfirmationCode:
        code,
    },
  );
}


export async function resendConfirmationCode(
  email: string,
) {
  return cognitoRequest(
    "ResendConfirmationCode",
    {
      ClientId:
        CLIENT_ID,

      Username:
        email,
    },
  );
}


export async function requestPasswordReset(
  email: string,
) {
  return cognitoRequest(
    "ForgotPassword",
    {
      ClientId:
        CLIENT_ID,

      Username:
        email,
    },
  );
}


export async function confirmPasswordReset(
  email: string,
  code: string,
  newPassword: string,
) {
  return cognitoRequest(
    "ConfirmForgotPassword",
    {
      ClientId:
        CLIENT_ID,

      Username:
        email,

      ConfirmationCode:
        code,

      Password:
        newPassword,
    },
  );
}


export async function provisionAccount(
  accessToken: string,
  name: string,
  organizationName: string,
  marketingContext?: Record<string, unknown> | null,
  registrationChannel: "direct" | "shopify_install" = "direct",
) {
  const apiUrl =
    import.meta.env.VITE_API_URL ||
    "http://127.0.0.1:8000";

  const response = await fetch(
    `${apiUrl}/api/register/provision`,
    {
      method: "POST",

      headers: {
        "Content-Type":
          "application/json",

        Authorization:
          `Bearer ${accessToken}`,
      },

      body: JSON.stringify({
        name,
        organization_name:
          organizationName,
        marketing_context:
          marketingContext || undefined,
        registration_channel: registrationChannel,
      }),
    },
  );

  const raw =
    await response.text();

  let data: unknown = {};

  if (raw) {
    try {
      data = JSON.parse(raw);
    } catch {
      data = {};
    }
  }

  if (!response.ok) {
    // Provisioning errors can contain validation/database/provider details.
    // Keep them in server logs; the login UI receives a stable code only.
    throw new AuthError("ACCOUNT_PROVISION_FAILED");
  }

  return data;
}


export async function refreshSession(
  refreshToken: string,
) {
  const data =
    (await cognitoRequest(
      "InitiateAuth",
      {
        AuthFlow:
          "REFRESH_TOKEN_AUTH",

        ClientId:
          CLIENT_ID,

        AuthParameters: {
          REFRESH_TOKEN:
            refreshToken,
        },
      },
    )) as CognitoAuthResponse;

  if (!data.AuthenticationResult) {
    throw new AuthError("SESSION_REFRESH_FAILED");
  }

  return data.AuthenticationResult;
}
