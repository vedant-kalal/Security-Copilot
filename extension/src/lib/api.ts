/**
 * Typed fetch wrapper for the security-copilot backend. The backend has
 * no auth (backend/README.md — POC scope), so this is just a base-URL
 * lookup + JSON in/out, backed by chrome.storage.local (async) since
 * this code runs in the background service worker and popup/options.
 */
import { getStorage } from "@/lib/storage";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const { apiBaseUrl } = await getStorage();

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, `Could not reach ${apiBaseUrl} — is the backend running? Check the URL in Settings.`);
  }

  if (!response.ok) {
    let message = response.statusText;
    try {
      const errorBody = (await response.json()) as { detail?: string };
      if (errorBody.detail) message = errorBody.detail;
    } catch {
      // no JSON body
    }
    throw new ApiError(response.status, message);
  }

  return (await response.json()) as T;
}

export const api = { post };
