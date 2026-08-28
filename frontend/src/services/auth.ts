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

  const data =
    await response.json();

  if (!response.ok) {
    const message =
      data.message ||
      data.Message ||
      "Authentication failed";

    throw new Error(message);
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
    throw new Error(
      "Cognito did not return authentication tokens",
    );
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


export async function provisionAccount(
  accessToken: string,
  name: string,
  organizationName: string,
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
      }),
    },
  );

  const raw =
    await response.text();

  let data: any = {};

  if (raw) {
    try {
      data = JSON.parse(raw);
    } catch {
      data = {
        detail: raw,
      };
    }
  }

  if (!response.ok) {
    const detail =
      typeof data?.detail === "string"
        ? data.detail
        : data?.detail?.message;

    throw new Error(
      detail ||
      "ACCOUNT_PROVISION_FAILED",
    );
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
    throw new Error(
      "Unable to refresh session",
    );
  }

  return data.AuthenticationResult;
}
