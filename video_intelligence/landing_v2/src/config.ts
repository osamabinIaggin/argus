/**
 * Base URL for the main app (try, developers, docs).
 * In dev: defaults to main app on port 5174. Set VITE_APP_URL to override.
 * In prod: use same origin (empty) when deployed together.
 */
export const APP_BASE =
  import.meta.env.VITE_APP_URL ||
  (import.meta.env.DEV ? 'http://localhost:5174' : '')

export const urls = {
  try: `${APP_BASE}/try`,
  developers: `${APP_BASE}/developers`,
  docs: `${APP_BASE}/docs`,
  dashboard: `${APP_BASE}/dashboard`,
}
