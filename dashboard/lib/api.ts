/**
 * Typed fetch wrapper for the Security Copilot backend. The backend has no auth
 * (backend/README.md — POC scope), so this is just a base-URL lookup + JSON
 * in/out. The base URL lives in localStorage under `apiBaseUrl` (same key name
 * the extension uses in chrome.storage.local; a web page can't read the
 * extension's store, so they can't literally share it, but the key/default
 * match so config stays familiar).
 */
import type { CheckLinksStreamEvent } from '@/lib/types'

const STORAGE_KEY = 'apiBaseUrl'
// A user-set base URL in Settings (localStorage) always wins. Absent that, the
// launch scripts inject the backend's real address via NEXT_PUBLIC_API_BASE_URL
// (they run it on :8010, not this default); the hardcoded value is the last
// resort for `pnpm dev` with nothing configured.
const ENV_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL?.trim()
const DEFAULT_BASE_URL = ENV_BASE_URL || 'http://localhost:8000'

export function getApiBaseUrl(): string {
  if (typeof window === 'undefined') return DEFAULT_BASE_URL
  return window.localStorage.getItem(STORAGE_KEY) || DEFAULT_BASE_URL
}

export function setApiBaseUrl(url: string): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(STORAGE_KEY, url.trim())
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function unreachable(base: string): ApiError {
  return new ApiError(0, `Could not reach ${base} — is the backend running? Check the URL in Settings.`)
}

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = response.statusText
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // no JSON body
    }
    throw new ApiError(response.status, message)
  }
  return (await response.json()) as T
}

export async function apiGet<T>(path: string): Promise<T> {
  const base = getApiBaseUrl()
  let response: Response
  try {
    response = await fetch(`${base}${path}`)
  } catch {
    throw unreachable(base)
  }
  return handle<T>(response)
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const base = getApiBaseUrl()
  let response: Response
  try {
    response = await fetch(`${base}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw unreachable(base)
  }
  return handle<T>(response)
}

/**
 * POST a request and consume the Server-Sent Events response as an async
 * iterator of parsed events. Used by the Link scanner to render the agent's
 * live progress (backend/api/routes_check_links_stream.py).
 */
export async function* apiPostStream(
  path: string,
  body: unknown,
): AsyncGenerator<CheckLinksStreamEvent> {
  const base = getApiBaseUrl()
  let response: Response
  try {
    response = await fetch(`${base}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw unreachable(base)
  }
  if (!response.ok || !response.body) {
    await handle(response) // throws ApiError with the backend's detail
    throw new ApiError(response.status, response.statusText)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let boundary: number
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const chunk = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const dataLine = chunk.split('\n').find((line) => line.startsWith('data:'))
      if (!dataLine) continue
      const json = dataLine.slice(5).trim()
      if (!json) continue
      yield JSON.parse(json) as CheckLinksStreamEvent
    }
  }
}
