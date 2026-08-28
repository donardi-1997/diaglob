import axios from "axios";

import {
  clearSession,
  getAccessToken,
  getRefreshToken,
  saveSession,
} from "./authStorage";

import {
  refreshSession,
} from "./auth";


export const api = axios.create({
  baseURL:
    import.meta.env.VITE_API_URL ||
    "http://127.0.0.1:8000",

  timeout: 10000,

  headers: {
    "Content-Type": "application/json",
  },
});


api.interceptors.request.use(
  (config) => {
    const accessToken =
      getAccessToken();

    const storeId =
      localStorage.getItem(
        "diaglob-store-id",
      );

    const globalScope =
      config.headers[
        "X-Diaglob-Global-Scope"
      ] === "1";

    delete config.headers[
      "X-Diaglob-Global-Scope"
    ];

    if (accessToken) {
      config.headers.Authorization =
        `Bearer ${accessToken}`;
    } else {
      delete config.headers.Authorization;
    }

    if (
      storeId &&
      !globalScope
    ) {
      config.headers[
        "X-Store-Id"
      ] = storeId;
    } else {
      delete config.headers[
        "X-Store-Id"
      ];
    }

    return config;
  },
);


let refreshPromise:
  Promise<string> | null = null;


function expireSession() {
  clearSession();

  window.dispatchEvent(
    new Event(
      "diaglob-auth-expired",
    ),
  );
}


async function getFreshAccessToken() {
  if (refreshPromise) {
    return refreshPromise;
  }

  const refreshToken =
    getRefreshToken();

  if (!refreshToken) {
    throw new Error(
      "Refresh token not available",
    );
  }

  refreshPromise =
    refreshSession(
      refreshToken,
    )
      .then((result) => {
        saveSession(
          result.AccessToken,
          result.IdToken,
        );

        return result.AccessToken;
      })
      .finally(() => {
        refreshPromise = null;
      });

  return refreshPromise;
}


api.interceptors.response.use(
  (response) => response,

  async (error) => {
    // ========================================================
    // PLAN REQUERIDO
    // ========================================================

    const responseStatus =
      error.response?.status;

    const responseDetail =
      error.response?.data?.detail;

    if (
      responseStatus === 402 &&
      responseDetail?.code === "PLAN_REQUIRED"
    ) {
      window.dispatchEvent(
        new CustomEvent(
          "diaglob-plan-required",
          {
            detail: {
              message:
                responseDetail.message,
            },
          },
        ),
      );

      return Promise.reject(error);
    }

    // ========================================================
    // AUTH / REFRESH TOKEN
    // ========================================================

    const originalRequest =
      error.config;

    if (
      responseStatus !== 401 ||
      !originalRequest
    ) {
      return Promise.reject(error);
    }

    if (originalRequest._retry) {
      expireSession();

      return Promise.reject(error);
    }

    const refreshToken =
      getRefreshToken();

    if (!refreshToken) {
      expireSession();

      return Promise.reject(error);
    }

    originalRequest._retry = true;

    try {
      const newAccessToken =
        await getFreshAccessToken();

      originalRequest.headers =
        originalRequest.headers || {};

      originalRequest.headers.Authorization =
        `Bearer ${newAccessToken}`;

      return api.request(
        originalRequest,
      );

    } catch (refreshError) {
      expireSession();

      return Promise.reject(
        refreshError,
      );
    }
  },
);
