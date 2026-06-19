/**
 * AuthContext — manages the user's JWT session.
 *
 * Stores access_token + refresh_token in localStorage for simplicity.
 * In production upgrade to an httpOnly cookie for the refresh token to
 * prevent XSS theft.
 *
 * The access token is also kept in memory (_token) so that apiFetch can
 * read it synchronously without coupling to React lifecycle.
 *
 * Auto-refresh: apiFetch calls refreshSession() on 401.  AuthContext
 * registers the callback so that every failed API call can transparently
 * rotate tokens without the component knowing.
 */
import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react'
import { setAuthToken, setRefreshCallback } from '../api/client'

export interface UserInfo {
  id:           string
  email:        string
  display_name: string | null
  plan:         string
}

interface AuthContextValue {
  user:         UserInfo | null
  accessToken:  string | null
  isLoading:    boolean          // true while rehydrating from localStorage on mount
  login:        (accessToken: string, refreshToken: string, user: UserInfo) => void
  logout:       () => void
  updateTokens: (accessToken: string, refreshToken: string) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

const STORAGE_KEYS = {
  access:  'vi_access_token',
  refresh: 'vi_refresh_token',
  user:    'vi_user',
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user,        setUser]        = useState<UserInfo | null>(null)
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [isLoading,   setIsLoading]   = useState(true)

  // Rehydrate session from localStorage on mount.
  useEffect(() => {
    const storedAccess  = localStorage.getItem(STORAGE_KEYS.access)
    const storedUser    = localStorage.getItem(STORAGE_KEYS.user)
    if (storedAccess && storedUser) {
      try {
        const parsed = JSON.parse(storedUser) as UserInfo
        setUser(parsed)
        setAccessToken(storedAccess)
        setAuthToken(storedAccess)
      } catch {
        // Corrupted storage — clear it.
        localStorage.removeItem(STORAGE_KEYS.access)
        localStorage.removeItem(STORAGE_KEYS.refresh)
        localStorage.removeItem(STORAGE_KEYS.user)
      }
    }
    setIsLoading(false)
  }, [])

  const login = useCallback((at: string, rt: string, u: UserInfo) => {
    localStorage.setItem(STORAGE_KEYS.access,  at)
    localStorage.setItem(STORAGE_KEYS.refresh, rt)
    localStorage.setItem(STORAGE_KEYS.user,    JSON.stringify(u))
    setUser(u)
    setAccessToken(at)
    setAuthToken(at)
  }, [])

  const updateTokens = useCallback((at: string, rt: string) => {
    localStorage.setItem(STORAGE_KEYS.access,  at)
    localStorage.setItem(STORAGE_KEYS.refresh, rt)
    setAccessToken(at)
    setAuthToken(at)
  }, [])

  const logout = useCallback(() => {
    // Best-effort: tell the server to revoke the refresh token.
    const rt = localStorage.getItem(STORAGE_KEYS.refresh)
    if (rt) {
      fetch('/v1/auth/logout', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ refresh_token: rt }),
      }).catch(() => { /* ignore — local state is cleared either way */ })
    }
    localStorage.removeItem(STORAGE_KEYS.access)
    localStorage.removeItem(STORAGE_KEYS.refresh)
    localStorage.removeItem(STORAGE_KEYS.user)
    setUser(null)
    setAccessToken(null)
    setAuthToken(null)
  }, [])

  // Wire the auto-refresh callback so apiFetch can rotate tokens on 401.
  useEffect(() => {
    setRefreshCallback(async () => {
      const rt = localStorage.getItem(STORAGE_KEYS.refresh)
      if (!rt) return null

      try {
        const res = await fetch('/v1/auth/refresh', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ refresh_token: rt }),
        })
        if (!res.ok) {
          logout()
          return null
        }
        const data = await res.json() as {
          access_token: string
          refresh_token: string
          user: UserInfo
        }
        updateTokens(data.access_token, data.refresh_token)
        // Also update stored user info if it changed.
        if (data.user) {
          localStorage.setItem(STORAGE_KEYS.user, JSON.stringify(data.user))
          setUser(data.user)
        }
        return data.access_token
      } catch {
        logout()
        return null
      }
    })
    // Clean up on unmount.
    return () => setRefreshCallback(null)
  }, [logout, updateTokens])

  return (
    <AuthContext.Provider value={{ user, accessToken, isLoading, login, logout, updateTokens }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
