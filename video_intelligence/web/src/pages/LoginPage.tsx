import { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'
import { GoogleLogin, useGoogleLogin } from '@react-oauth/google'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { Input } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

/** Returns true when running as an installed PWA (standalone mode). */
function isPwa(): boolean {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    // iOS Safari sets navigator.standalone
    (navigator as unknown as { standalone?: boolean }).standalone === true
  )
}

export default function LoginPage() {
  const { login } = useAuth()
  const navigate  = useNavigate()

  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')
  const [pwa]      = useState(isPwa)

  // The redirect URI we tell Google (must also be registered in Google Console).
  const redirectUri = `${window.location.origin}/login`

  const handleGoogle = useCallback(async (credential: string) => {
    setError('')
    setLoading(true)
    try {
      const res = await api.googleAuth(credential)
      if (res.api_key) localStorage.setItem('vi_api_key', res.api_key)
      login(res.access_token, res.refresh_token, res.user)
      navigate('/dashboard')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Google sign-in failed')
    } finally {
      setLoading(false)
    }
  }, [login, navigate])

  // Handle OAuth2 code returned by redirect flow (PWA mode).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const code   = params.get('code')
    if (!code) return

    // Clean up the URL so a page refresh doesn't re-submit the code.
    window.history.replaceState({}, '', '/login')

    setLoading(true)
    setError('')
    api.googleCodeExchange(code, redirectUri)
      .then((res) => {
        if (res.api_key) localStorage.setItem('vi_api_key', res.api_key)
        login(res.access_token, res.refresh_token, res.user)
        navigate('/dashboard')
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Google sign-in failed')
        setLoading(false)
      })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // PWA redirect-based Google sign-in via useGoogleLogin.
  const startGoogleRedirect = useGoogleLogin({
    flow:         'auth-code',
    ux_mode:      'redirect',
    redirect_uri: redirectUri,
    scope:        'openid email profile',
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email || !password) { setError('Email and password are required'); return }
    setError('')
    setLoading(true)
    try {
      const res = await api.login(email.trim().toLowerCase(), password)
      login(res.access_token, res.refresh_token, res.user)
      navigate('/dashboard')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-page flex flex-col" style={{ paddingTop: 'env(safe-area-inset-top)' }}>
      {/* Nav */}
      <nav className="border-b border-divider">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center">
          <Link to="/" className="flex items-center gap-2 font-semibold text-text-1">
            <img src="/icon-192.png" alt="" className="w-5 h-5 rounded" />
            Video Intelligence
          </Link>
        </div>
      </nav>

      {/* Form */}
      <div className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 text-center">
            <h1 className="text-2xl font-bold text-text-1 mb-1">Welcome back</h1>
            <p className="text-sm text-text-2">Sign in to your account</p>
          </div>

          <Card className="flex flex-col gap-4">
            {/* Google sign-in */}
            <div className="flex justify-center">
              {pwa ? (
                /* PWA standalone: use full-page redirect — no popup */
                <button
                  onClick={() => startGoogleRedirect()}
                  disabled={loading}
                  className="w-full flex items-center justify-center gap-3 px-4 py-2.5 rounded-lg border border-divider bg-surface text-text-1 text-sm font-medium hover:bg-surface-2 transition-colors disabled:opacity-50"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                  </svg>
                  Sign in with Google
                </button>
              ) : (
                /* Browser: use GIS One Tap popup */
                <GoogleLogin
                  onSuccess={(res) => {
                    if (res.credential) handleGoogle(res.credential)
                  }}
                  onError={() => setError('Google sign-in failed')}
                  theme="outline"
                  size="large"
                  width="100%"
                  text="signin_with"
                />
              )}
            </div>

            <div className="flex items-center gap-3">
              <div className="flex-1 h-px bg-divider" />
              <span className="text-xs text-text-3">or</span>
              <div className="flex-1 h-px bg-divider" />
            </div>

            {/* Email / password */}
            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              <Input
                label="Email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
              />
              <Input
                label="Password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />

              {error && (
                <div className="flex items-center gap-2 text-sm text-error">
                  <AlertCircle size={14} className="shrink-0" />
                  {error}
                </div>
              )}

              <Button type="submit" loading={loading} className="w-full mt-1">
                Sign in
              </Button>
            </form>
          </Card>

          <p className="text-center text-sm text-text-2 mt-6">
            Don't have an account?{' '}
            <Link to="/register" className="text-accent hover:underline font-medium">
              Create one free
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
