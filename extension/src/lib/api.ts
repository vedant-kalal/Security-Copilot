/**
 * Typed fetch wrapper for the SentinelAI API, mirroring
 * dashboard/src/lib/api-client.ts but backed by chrome.storage.local
 * (async) instead of localStorage (sync), since this code runs in the
 * extension's background service worker, popup, and options contexts.
 */
import { getStorage, setStorage } from "@/lib/storage";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

async function refreshAccessToken(): Promise<boolean> {
  const { apiBaseUrl, refreshToken } = await getStorage();
  if (!refreshToken) return false;

  const response = await fetch(`${apiBaseUrl}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) return false;

  const tokens = (await response.json()) as TokenResponse;
  await setStorage({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token });
  return true;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  skipAuth?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}, isRetry = false): Promise<T> {
  const { apiBaseUrl, accessToken } = await getStorage();
  const headers: Record<string, string> = {};
  let body: string | undefined;

  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  if (!options.skipAuth && accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }

  const response = await fetch(`${apiBaseUrl}${path}`, { method: options.method ?? "GET", headers, body });

  if (response.status === 401 && !options.skipAuth && !isRetry) {
    const refreshed = await refreshAccessToken();
    if (refreshed) return request<T>(path, options, true);
    throw new ApiError(401, "unauthorized", "Session expired. Please sign in again.");
  }

  if (!response.ok) {
    let message = response.statusText;
    let code = "unknown_error";
    try {
      const errorBody = (await response.json()) as { error?: { code?: string; message?: string } };
      message = errorBody.error?.message ?? message;
      code = errorBody.error?.code ?? code;
    } catch {
      // no JSON body
    }
    throw new ApiError(response.status, code, message);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown, skipAuth = false) => request<T>(path, { method: "POST", body, skipAuth }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
};

export type { TokenResponse };
