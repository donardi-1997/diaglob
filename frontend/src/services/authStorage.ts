const ACCESS_TOKEN_KEY =
  "diaglob-access-token";

const ID_TOKEN_KEY =
  "diaglob-id-token";

const REFRESH_TOKEN_KEY =
  "diaglob-refresh-token";


export function saveSession(
  accessToken: string,
  idToken: string,
  refreshToken?: string,
) {
  localStorage.setItem(
    ACCESS_TOKEN_KEY,
    accessToken,
  );

  localStorage.setItem(
    ID_TOKEN_KEY,
    idToken,
  );

  if (refreshToken) {
    localStorage.setItem(
      REFRESH_TOKEN_KEY,
      refreshToken,
    );
  }
}


export function getAccessToken() {
  return localStorage.getItem(
    ACCESS_TOKEN_KEY,
  );
}


export function getRefreshToken() {
  return localStorage.getItem(
    REFRESH_TOKEN_KEY,
  );
}


export function clearSession() {
  localStorage.removeItem(
    ACCESS_TOKEN_KEY,
  );

  localStorage.removeItem(
    ID_TOKEN_KEY,
  );

  localStorage.removeItem(
    REFRESH_TOKEN_KEY,
  );

  localStorage.removeItem(
    "diaglob-organization-id",
  );

  localStorage.removeItem(
    "diaglob-store-id",
  );

  localStorage.removeItem(
    "diaglob-user-id",
  );
}


export function hasSession() {
  return Boolean(
    getAccessToken(),
  );
}
