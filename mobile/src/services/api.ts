import { refreshSession } from "./auth";
import { API_URL } from "./config";
import {
  clearSession,
  getOrganizationId,
  getStoreId,
  getTokens,
  saveTokens,
} from "./storage";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(
    message: string,
    status: number,
    detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

interface ApiOptions extends RequestInit {
  globalScope?: boolean;
  storeId?: string | null;
  retried?: boolean;
}

async function parseResponse(response: Response) {
  const raw = await response.text();
  if (!raw) return null;

  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

export async function apiRequest<T>(
  path: string,
  options: ApiOptions = {},
): Promise<T> {
  const [
    tokens,
    organizationId,
    savedStoreId,
  ] = await Promise.all([
    getTokens(),
    getOrganizationId(),
    getStoreId(),
  ]);

  const headers = new Headers(options.headers);

  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (tokens.accessToken) {
    headers.set(
      "Authorization",
      `Bearer ${tokens.accessToken}`,
    );
  }

  if (organizationId) {
    headers.set("X-Organization-Id", organizationId);
  }

  const effectiveStoreId =
    options.storeId === undefined
      ? savedStoreId
      : options.storeId;

  if (effectiveStoreId && !options.globalScope) {
    headers.set("X-Store-Id", effectiveStoreId);
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  if (
    response.status === 401 &&
    !options.retried &&
    tokens.refreshToken
  ) {
    try {
      const refreshed = await refreshSession(
        tokens.refreshToken,
      );
      await saveTokens(
        refreshed.AccessToken,
        refreshed.IdToken,
        tokens.refreshToken,
      );
      return apiRequest<T>(path, {
        ...options,
        retried: true,
      });
    } catch {
      await clearSession();
      throw new ApiError(
        "Tu sesión expiró. Inicia sesión nuevamente.",
        401,
      );
    }
  }

  const data = await parseResponse(response);

  if (!response.ok) {
    const detail =
      typeof data === "object" && data
        ? (data as { detail?: unknown }).detail
        : data;

    const message =
      typeof detail === "string"
        ? detail
        : "No fue posible completar la solicitud.";

    throw new ApiError(message, response.status, detail);
  }

  return data as T;
}
