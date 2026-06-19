/**
 * API client — typed wrappers around fetch.
 *
 * Auth token priority:
 *   1. _token  (JWT set by AuthContext on login / token refresh)
 *   2. localStorage 'vi_api_key'  (legacy API-key-only flow, still supported)
 *
 * Auto-refresh: on 401, calls _refreshCallback (wired by AuthContext) to
 * rotate tokens, then retries the original request once.
 */

// ---------------------------------------------------------------------------
// Module-level auth state — updated by AuthContext, read by apiFetch.
// ---------------------------------------------------------------------------

let _token: string | null = null
let _refreshCallback: (() => Promise<string | null>) | null = null
// Shared in-flight promise so concurrent 401s only trigger one refresh.
let _refreshPromise: Promise<string | null> | null = null

export function setAuthToken(token: string | null): void {
  _token = token
}

export function setRefreshCallback(cb: (() => Promise<string | null>) | null): void {
  _refreshCallback = cb
}

function getToken(): string | null {
  // JWT takes priority; fall back to the legacy API key in localStorage.
  return _token ?? localStorage.getItem('vi_api_key')
}

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name   = 'ApiError'
    this.status = status
  }
}

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

interface FetchOptions extends Omit<RequestInit, 'headers'> {
  headers?:   Record<string, string>
  /** Skip Content-Type so the browser sets the multipart boundary. */
  multipart?: boolean
  /** Internal flag — prevents infinite retry loops on 401. */
  _retry?: boolean
}

export async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { multipart, _retry, ...rest } = options
  const token = getToken()

  const headers: Record<string, string> = {
    ...(multipart ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  }

  const url = path.startsWith('/v1') || path.startsWith('/v1/auth') ? path : `/v1${path}`
  const res  = await fetch(url, { ...rest, headers })

  // Auto-refresh: if 401 and we haven't already retried, attempt token rotation.
  // All concurrent 401s share one in-flight refresh promise to avoid rotating
  // the same token twice (which the server treats as theft and revokes the family).
  if (res.status === 401 && !_retry && _refreshCallback) {
    if (!_refreshPromise) {
      _refreshPromise = _refreshCallback().finally(() => { _refreshPromise = null })
    }
    const newToken = await _refreshPromise
    if (newToken) {
      return apiFetch<T>(path, { ...options, _retry: true })
    }
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json() as { detail?: string; message?: string }
      detail = body.detail ?? body.message ?? detail
    } catch { /* ignore parse errors */ }
    throw new ApiError(detail, res.status)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// Typed API helpers
// ---------------------------------------------------------------------------

import type {
  AnalyzeResponse,
  StatusResponse,
  VideoResult,
  APIKeyInfo,
  JobListItem,
} from '../types'

import type { UserInfo } from '../context/AuthContext'

interface TokenResponse {
  access_token:  string
  refresh_token: string
  token_type:    string
  user:          UserInfo
  api_key?:      string   // present only on register / first Google login
}

export const api = {
  // ------------------------------------------------------------------
  // Auth
  // ------------------------------------------------------------------

  register: (name: string, email: string, password: string, plan = 'free') =>
    apiFetch<TokenResponse>('/v1/auth/register', {
      method: 'POST',
      body:   JSON.stringify({ name, email, password, plan }),
    }),

  login: (email: string, password: string) =>
    apiFetch<TokenResponse>('/v1/auth/login', {
      method: 'POST',
      body:   JSON.stringify({ email, password }),
    }),

  googleAuth: (credential: string) =>
    apiFetch<TokenResponse>('/v1/auth/google', {
      method: 'POST',
      body:   JSON.stringify({ credential }),
    }),

  googleCodeExchange: (code: string, redirectUri: string) =>
    apiFetch<TokenResponse>('/v1/auth/google/exchange', {
      method: 'POST',
      body:   JSON.stringify({ code, redirect_uri: redirectUri }),
    }),

  refreshTokens: (refreshToken: string) =>
    apiFetch<TokenResponse>('/v1/auth/refresh', {
      method: 'POST',
      body:   JSON.stringify({ refresh_token: refreshToken }),
    }),

  logout: (refreshToken: string) =>
    apiFetch<void>('/v1/auth/logout', {
      method: 'POST',
      body:   JSON.stringify({ refresh_token: refreshToken }),
    }),

  getMe: () => apiFetch<UserInfo>('/v1/auth/me'),

  // ------------------------------------------------------------------
  // API keys
  // ------------------------------------------------------------------

  /** Create a free API key (legacy no-auth endpoint, anonymous user). */
  createKey: (name: string, plan: string) =>
    apiFetch<{ key: string; name: string; plan: string }>('/v1/keys', {
      method: 'POST',
      body:   JSON.stringify({ name, plan }),
    }),

  getKeyInfo: () => apiFetch<APIKeyInfo>('/v1/keys/me'),

  revokeKey: (key: string) =>
    apiFetch<void>(`/v1/keys/${key}/revoke`, { method: 'POST' }),

  // ------------------------------------------------------------------
  // Jobs
  // ------------------------------------------------------------------

  listJobs: () => apiFetch<JobListItem[]>('/v1/jobs'),

  analyzeFile: (file: File, fps = 5) => {
    const form = new FormData()
    form.append('file', file)
    form.append('fps', String(fps))
    return apiFetch<AnalyzeResponse>('/v1/analyze', { method: 'POST', body: form, multipart: true })
  },

  analyzeUrl: (url: string, fps = 5) => {
    const form = new FormData()
    form.append('url', url)
    form.append('fps', String(fps))
    return apiFetch<AnalyzeResponse>('/v1/analyze', { method: 'POST', body: form, multipart: true })
  },

  getStatus: (videoId: string) => apiFetch<StatusResponse>(`/v1/status/${videoId}`),

  getResult: (videoId: string) => apiFetch<VideoResult>(`/v1/result/${videoId}`),

  deleteJob: (videoId: string) =>
    apiFetch<void>(`/v1/result/${videoId}`, { method: 'DELETE' }),

  // ------------------------------------------------------------------
  // Chat
  // ------------------------------------------------------------------

  chat: (videoId: string, message: string, history: { role: string; content: string }[] = []) =>
    apiFetch<{ response: string; video_id: string }>('/v1/chat', {
      method: 'POST',
      body:   JSON.stringify({ video_id: videoId, message, history }),
    }),

  getChatMessages: (videoId: string) =>
    apiFetch<{ id: string; role: string; content: string }[]>(`/v1/chats/${videoId}`),

  // ------------------------------------------------------------------
  // Push notifications
  // ------------------------------------------------------------------

  registerFcmToken: (token: string) =>
    apiFetch<void>('/v1/notifications/register', {
      method: 'POST',
      body:   JSON.stringify({ token }),
    }),

  // ------------------------------------------------------------------
  // PowerSync — real-time local-first sync
  // ------------------------------------------------------------------

  getPowerSyncToken: () =>
    apiFetch<{ token: string; powersync_url: string }>('/v1/powersync/token'),

  // ------------------------------------------------------------------
  // Library — cross-video Mastra agent
  // ------------------------------------------------------------------

  getLibraryMessages: () =>
    apiFetch<{ id: string; role: string; content: string }[]>('/v1/library/messages'),

  libraryChat: (message: string) =>
    apiFetch<{ response: string }>('/v1/library/chat', {
      method: 'POST',
      body:   JSON.stringify({ message }),
    }),
}
