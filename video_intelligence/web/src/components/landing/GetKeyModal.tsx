import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { AlertCircle, CheckCircle, LogIn } from 'lucide-react'
import { Modal } from '../ui/Modal'
import { Input } from '../ui/Input'
import { Button } from '../ui/Button'
import { CopyButton } from '../ui/CopyButton'
import { useApiKey } from '../../context/ApiKeyContext'
import { useAuth } from '../../context/AuthContext'
import { api } from '../../api/client'

type Step = 'form' | 'done'

const PLANS = [
  { value: 'free', label: 'Free', sub: '$0 · 60 min/mo' },
  { value: 'starter', label: 'Starter', sub: '$19 · 300 min/mo' },
]

interface GetKeyModalProps {
  open: boolean
  onClose: () => void
  /** When provided, called after key is saved instead of navigating to dashboard */
  onSuccess?: (key: string) => void
}

export function GetKeyModal({ open, onClose, onSuccess }: GetKeyModalProps) {
  const navigate = useNavigate()
  const { setApiKey } = useApiKey()
  const { user } = useAuth()

  const [step, setStep] = useState<Step>('form')
  const [name, setName] = useState('')
  const [plan, setPlan] = useState('free')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [newKey, setNewKey] = useState('')

  const handleCreate = async () => {
    if (!name.trim()) { setError('Name is required'); return }
    setError('')
    setLoading(true)
    try {
      const res = await api.createKey(name.trim(), plan)
      setNewKey(res.key)
      setStep('done')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create key')
    } finally {
      setLoading(false)
    }
  }

  const handleSuccess = () => {
    setApiKey(newKey)
    onClose()
    if (onSuccess) {
      onSuccess(newKey)
    } else {
      navigate('/dashboard')
    }
  }

  const handleClose = () => {
    onClose()
    // Reset after close animation
    setTimeout(() => {
      setStep('form')
      setName('')
      setPlan('free')
      setError('')
      setNewKey('')
    }, 200)
  }

  return (
    <Modal open={open} onClose={handleClose} title="Get your API key">
      {/* Auth gate — must be signed in to get a key */}
      {!user ? (
        <div className="flex flex-col items-center gap-5 py-2 text-center">
          <div className="w-12 h-12 rounded-full bg-accent/10 flex items-center justify-center">
            <LogIn size={22} className="text-accent" />
          </div>
          <div>
            <p className="text-sm font-medium text-text-1 mb-1">Sign in to get an API key</p>
            <p className="text-xs text-text-3 max-w-xs mx-auto">
              API keys are linked to your account so we can track usage and billing. Create a free account to continue.
            </p>
          </div>
          <div className="flex gap-3 w-full">
            <Link to="/register" className="flex-1" onClick={handleClose}>
              <Button className="w-full">Create account</Button>
            </Link>
            <Link to="/login" className="flex-1" onClick={handleClose}>
              <Button variant="secondary" className="w-full">Sign in</Button>
            </Link>
          </div>
        </div>
      ) : step === 'form' ? (
        <div className="flex flex-col gap-4">
          <Input
            label="Your name"
            placeholder="Alice Smith"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
          />

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-text-1">Plan</label>
            <div className="flex gap-2">
              {PLANS.map((p) => (
                <button
                  key={p.value}
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
              <AlertCircle size={14} />
              {error}
            </div>
          )}

          <Button onClick={handleCreate} loading={loading} className="w-full mt-1">
            Create key
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-5">
          <div className="flex items-center gap-2 text-success">
            <CheckCircle size={18} />
            <span className="font-medium">Key created successfully</span>
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2 bg-surface-2 rounded-lg px-3 py-2.5 border border-divider">
              <code className="flex-1 text-sm font-mono text-text-1 break-all">{newKey}</code>
              <CopyButton text={newKey} />
            </div>
            <div className="flex items-start gap-1.5 text-xs text-warning">
              <AlertCircle size={12} className="mt-0.5 shrink-0" />
              <span>Save this key — it won't be shown again.</span>
            </div>
          </div>

          <Button onClick={handleSuccess} className="w-full">
            {onSuccess ? 'Start analyzing' : 'Go to Dashboard →'}
          </Button>
        </div>
      )}
    </Modal>
  )
}
