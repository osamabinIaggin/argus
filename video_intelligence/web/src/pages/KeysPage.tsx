import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Eye, EyeOff, AlertTriangle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useApiKey } from '../context/ApiKeyContext'
import { Card } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { CopyButton } from '../components/ui/CopyButton'
import { Modal } from '../components/ui/Modal'
import { PLANS, type APIKeyInfo } from '../types'

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
  })
}

export default function KeysPage() {
  const { apiKey, clearApiKey } = useApiKey()
  const navigate = useNavigate()
  const [revealed, setRevealed] = useState(false)
  const [showRevokeModal, setShowRevokeModal] = useState(false)
  const [revoking, setRevoking] = useState(false)
  const [revokeError, setRevokeError] = useState('')

  const { data: keyInfo } = useQuery<APIKeyInfo>({
    queryKey: ['keyInfo'],
    queryFn: () => api.getKeyInfo(),
    enabled: !!apiKey,
  })

  const plan = keyInfo ? PLANS[keyInfo.plan] ?? PLANS['free'] : PLANS['free']
  const planMinutes = plan.minutes_per_month

  const displayKey = revealed
    ? (apiKey ?? '')
    : (keyInfo?.key ?? (apiKey ? apiKey.slice(0, 12) + '…' + apiKey.slice(-4) : '—'))

  const handleRevoke = async () => {
    if (!apiKey) return
    setRevoking(true)
    setRevokeError('')
    try {
      await api.revokeKey(apiKey)
      clearApiKey()
      navigate('/')
    } catch (e) {
      setRevokeError(e instanceof Error ? e.message : 'Revoke failed')
      setRevoking(false)
    }
  }

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <h1 className="text-2xl font-bold text-text-1">API Key</h1>

      {/* Key card */}
      <Card>
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-sm font-semibold text-text-1">Your API Key</h2>
          <Badge status={keyInfo?.is_active ? 'active' : 'inactive'} />
        </div>

        <div className="flex items-center gap-2 bg-surface-2 rounded-lg px-3 py-2.5 border border-divider mb-5">
          <code className="flex-1 text-sm font-mono text-text-1 break-all">{displayKey}</code>
          <button
            onClick={() => setRevealed((v) => !v)}
            className="p-1.5 rounded text-text-3 hover:text-text-1 hover:bg-surface transition-colors"
            title={revealed ? 'Hide key' : 'Reveal full key'}
          >
            {revealed ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
          {apiKey && <CopyButton text={apiKey} />}
        </div>

        <div className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
          <div>
            <span className="text-text-3 text-xs">Name</span>
            <p className="text-text-1 font-medium mt-0.5">{keyInfo?.name ?? '—'}</p>
          </div>
          <div>
            <span className="text-text-3 text-xs">Plan</span>
            <p className="text-text-1 font-medium mt-0.5 capitalize">{plan.label}</p>
          </div>
          <div>
            <span className="text-text-3 text-xs">Requests (all time)</span>
            <p className="text-text-1 font-medium mt-0.5">{keyInfo?.total_requests ?? 0}</p>
          </div>
          <div>
            <span className="text-text-3 text-xs">Created</span>
            <p className="text-text-1 font-medium mt-0.5">{formatDate(keyInfo?.created_at)}</p>
          </div>
          <div>
            <span className="text-text-3 text-xs">Last used</span>
            <p className="text-text-1 font-medium mt-0.5">{formatDate(keyInfo?.last_used_at)}</p>
          </div>
        </div>
      </Card>

      {/* Usage meter */}
      <Card>
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-sm font-semibold text-text-1">Usage this month</h2>
        </div>
        <p className="text-xs text-text-3">
          Usage tracking coming soon. Your plan allows{' '}
          {planMinutes === Infinity ? 'unlimited' : `${planMinutes} minutes per month`}.
        </p>
      </Card>

      {/* Danger zone */}
      <Card>
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-text-1">Revoke key</h2>
            <p className="text-xs text-text-3 mt-0.5">
              This immediately invalidates your key. All in-progress jobs will fail.
            </p>
          </div>
          <Button variant="danger" size="sm" onClick={() => setShowRevokeModal(true)}>
            Revoke key
          </Button>
        </div>
      </Card>

      {/* Revoke confirmation modal */}
      <Modal
        open={showRevokeModal}
        onClose={() => { setShowRevokeModal(false); setRevokeError('') }}
        title="Revoke API key?"
      >
        <div className="flex flex-col gap-4">
          <div className="flex items-start gap-3 p-3 bg-red-50 rounded-lg border border-red-200">
            <AlertTriangle size={16} className="text-error shrink-0 mt-0.5" />
            <p className="text-sm text-error">
              This cannot be undone. Your key will stop working immediately and you'll be logged out.
            </p>
          </div>

          {revokeError && (
            <p className="text-sm text-error">{revokeError}</p>
          )}

          <div className="flex gap-3">
            <Button
              variant="secondary"
              className="flex-1"
              onClick={() => setShowRevokeModal(false)}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              className="flex-1"
              loading={revoking}
              onClick={handleRevoke}
            >
              Yes, revoke
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
