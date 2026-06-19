import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Video, AlertCircle, CheckCircle } from 'lucide-react'
import { GoogleLogin } from '@react-oauth/google'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { Input } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { CopyButton } from '../components/ui/CopyButton'

type Step = 'form' | 'api-key'

const PLANS = [
  { value: 'free',    label: 'Free',    sub: '$0 · 60 min/mo' },
  { value: 'starter', label: 'Starter', sub: '$19 · 300 min/mo' },
]

export default function RegisterPage() {
  const { login } = useAuth()
  const navigate  = useNavigate()

  const [step,     setStep]     = useState<Step>('form')
  const [name,     setName]     = useState('')
  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [plan,     setPlan]     = useState('free')
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')
  const [apiKey,   setApiKey]   = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim())  { setError('Name is required');  return }
    if (!email.trim()) { setError('Email is required'); return }
    if (password.length < 8) { setError('Password must be at least 8 characters'); return }
    setError('')
    setLoading(true)
    try {
      const res = await api.register(name.trim(), email.trim().toLowerCase(), password, plan)
      login(res.access_token, res.refresh_token, res.user)
      // Persist the API key for legacy components that read from localStorage.
      if (res.api_key) {
        localStorage.setItem('vi_api_key', res.api_key)
        setApiKey(res.api_key)
        setStep('api-key')
      } else {
        navigate('/dashboard')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  const handleGoogle = async (credential: string) => {
    setError('')
    setLoading(true)
    try {
      const res = await api.googleAuth(credential)
      login(res.access_token, res.refresh_token, res.user)
      if (res.api_key) {
        localStorage.setItem('vi_api_key', res.api_key)
        setApiKey(res.api_key)
        setStep('api-key')
      } else {
        // Existing Google account — go straight to dashboard.
        navigate('/dashboard')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Google sign-in failed')
    } finally {
      setLoading(false)
    }
  }

  if (step === 'api-key') {
    return (
      <div className="min-h-screen bg-page flex flex-col">
        <nav className="border-b border-divider">
          <div className="max-w-6xl mx-auto px-6 h-14 flex items-center">
            <Link to="/" className="flex items-center gap-2 font-semibold text-text-1">
              <Video size={20} className="text-accent" />
              Video Intelligence
            </Link>
          </div>
        </nav>

        <div className="flex-1 flex items-center justify-center px-6 py-12">
          <div className="w-full max-w-sm">
            <Card className="flex flex-col gap-5">
              <div className="flex items-center gap-2 text-success">
                <CheckCircle size={20} />
                <span className="font-semibold text-text-1">Account created!</span>
              </div>

              <div>
                <p className="text-sm font-medium text-text-1 mb-2">Your API key</p>
                <div className="flex items-center gap-2 bg-surface-2 border border-divider rounded-lg px-3 py-2.5">
                  <code className="flex-1 text-sm font-mono text-text-1 break-all">{apiKey}</code>
                  <CopyButton text={apiKey} />
                </div>
                <div className="flex items-start gap-1.5 mt-2 text-xs text-warning">
                  <AlertCircle size={12} className="mt-0.5 shrink-0" />
                  <span>Save this key — it won't be shown again. Use it in your API requests.</span>
                </div>
              </div>

              <Button onClick={() => navigate('/dashboard')} className="w-full">
                Go to dashboard →
              </Button>
            </Card>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-page flex flex-col">
      {/* Nav */}
      <nav className="border-b border-divider">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center">
          <Link to="/" className="flex items-center gap-2 font-semibold text-text-1">
            <Video size={20} className="text-accent" />
            Video Intelligence
          </Link>
        </div>
      </nav>

      {/* Form */}
      <div className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 text-center">
            <h1 className="text-2xl font-bold text-text-1 mb-1">Create your account</h1>
            <p className="text-sm text-text-2">Free tier: 60 min/month · No credit card</p>
          </div>

          <Card className="flex flex-col gap-4">
            {/* Google sign-up */}
            <div className="flex justify-center">
              <GoogleLogin
                onSuccess={(res) => {
                  if (res.credential) handleGoogle(res.credential)
                }}
                onError={() => setError('Google sign-in failed')}
                theme="outline"
                size="large"
                width="100%"
                text="signup_with"
              />
            </div>

            <div className="flex items-center gap-3">
              <div className="flex-1 h-px bg-divider" />
              <span className="text-xs text-text-3">or</span>
              <div className="flex-1 h-px bg-divider" />
            </div>

            {/* Email / password */}
            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              <Input
                label="Full name"
                placeholder="Alice Smith"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
              />
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
                placeholder="Min 8 characters"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />

              {/* Plan selector */}
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-text-1">Plan</label>
                <div className="flex gap-2">
                  {PLANS.map((p) => (
                    <button
                      key={p.value}
                      type="button"
                      onClick={() => setPlan(p.value)}
                      className={[
                        'flex-1 text-left px-3 py-2.5 rounded-lg border text-sm transition-colors',
                        plan === p.value
                          ? 'border-accent bg-accent/5 text-accent'
                          : 'border-divider bg-surface text-text-2 hover:border-text-3',
                      ].join(' ')}
                    >
                      <div className="font-medium">{p.label}</div>
                      <div className="text-xs opacity-75 mt-0.5">{p.sub}</div>
                    </button>
                  ))}
                </div>
              </div>

              {error && (
                <div className="flex items-center gap-2 text-sm text-error">
                  <AlertCircle size={14} className="shrink-0" />
                  {error}
                </div>
              )}

              <Button type="submit" loading={loading} className="w-full mt-1">
                Create account
              </Button>
            </form>
          </Card>

          <p className="text-center text-sm text-text-2 mt-6">
            Already have an account?{' '}
            <Link to="/login" className="text-accent hover:underline font-medium">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
