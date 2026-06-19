import { useState } from 'react'
import { NavLink, useNavigate, useParams } from 'react-router-dom'
import {
  Plus,
  Key,
  BookOpen,
  Video,
  LogOut,
  Clock,
  Trash2,
  X,
  Library,
} from 'lucide-react'
import { SyncStatus } from './SyncStatus'
import { InstallPrompt } from './InstallPrompt'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../../context/AuthContext'
import { useJobs } from '../../hooks/useJobs'
import { api } from '../../api/client'
import { ConfirmDialog } from '../ui/ConfirmDialog'
import type { JobListItem } from '../../types'

const bottomItems = [
  { to: '/library', label: 'Library',  icon: Library },
  { to: '/keys',    label: 'API Key',  icon: Key },
  { to: '/docs',    label: 'Docs',     icon: BookOpen },
]

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function statusDot(status: JobListItem['status']) {
  if (status === 'complete')
    return <span className="w-1.5 h-1.5 rounded-full bg-success shrink-0" />
  if (status === 'processing' || status === 'queued')
    return <span className="w-1.5 h-1.5 rounded-full bg-warning animate-pulse shrink-0" />
  return <span className="w-1.5 h-1.5 rounded-full bg-error shrink-0" />
}

interface SidebarProps {
  onClose?: () => void
}

export function Sidebar({ onClose }: SidebarProps) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { videoId: activeVideoId } = useParams<{ videoId?: string }>()
  const queryClient = useQueryClient()
  const { data: jobs = [] } = useJobs()

  const [pendingDelete, setPendingDelete] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [confirmLogout, setConfirmLogout] = useState(false)

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  const requestDelete = (e: React.MouseEvent, videoId: string) => {
    e.preventDefault()
    e.stopPropagation()
    setPendingDelete(videoId)
  }

  const confirmDelete = async () => {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      await api.deleteJob(pendingDelete)
      queryClient.setQueryData<JobListItem[]>(['jobs'], (old) =>
        (old ?? []).filter((j) => j.video_id !== pendingDelete)
      )
      localStorage.removeItem(`vi_chat_${pendingDelete}`)
      if (activeVideoId === pendingDelete) navigate('/jobs')
    } finally {
      setDeleting(false)
      setPendingDelete(null)
    }
  }

  const handleNavClick = () => {
    onClose?.()
  }

  return (
    <aside
      className="w-64 md:w-60 shrink-0 h-[100dvh] bg-surface-2 border-r border-divider flex flex-col"
      style={{ paddingTop: 'env(safe-area-inset-top)' }}
    >
      {/* Logo + action button */}
      <div className="px-3 pt-4 pb-2 flex items-center gap-2">
        <div className="flex items-center gap-2 flex-1 min-w-0 px-1">
          <Video size={16} className="text-accent shrink-0" />
          <span className="font-semibold text-text-1 text-sm truncate">Video Intelligence</span>
        </div>
        {onClose ? (
          /* Mobile: show X to close drawer */
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-text-2 hover:bg-surface hover:text-text-1 transition-colors shrink-0"
            aria-label="Close menu"
          >
            <X size={16} />
          </button>
        ) : (
          /* Desktop: show + for new analysis */
          <button
            onClick={() => navigate('/playground')}
            title="New analysis"
            className="p-1.5 rounded-lg text-text-2 hover:bg-surface hover:text-text-1 transition-colors shrink-0"
          >
            <Plus size={16} />
          </button>
        )}
      </div>

      {/* New Adventure link */}
      <nav className="px-3 pb-2">
        <NavLink
          to="/playground"
          end
          onClick={handleNavClick}
          className={({ isActive }) =>
            [
              'flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm transition-colors',
              isActive
                ? 'bg-accent/10 text-accent font-medium'
                : 'text-text-2 hover:bg-surface hover:text-text-1',
            ].join(' ')
          }
        >
          <Plus size={16} />
          New Adventure
        </NavLink>
      </nav>

      {/* Recents — scrollable chat list */}
      <div className="flex-1 overflow-y-auto px-3 min-h-0">
        {jobs.length > 0 ? (
          <>
            <p className="text-[11px] font-medium text-text-3 uppercase tracking-wider px-3 mb-1.5 mt-1">
              Recents
            </p>
            <div className="flex flex-col gap-0.5">
              {jobs.map((job, idx) => {
                const title = job.summary
                  ? job.summary.slice(0, 55) + (job.summary.length > 55 ? '…' : '')
                  : job.video_id.slice(0, 18) + '…'

                return (
                  <NavLink
                    key={job.video_id}
                    to={`/jobs/${job.video_id}`}
                    onClick={handleNavClick}
                    style={{ '--stagger': idx } as React.CSSProperties}
                    className={({ isActive }) =>
                      [
                        'group flex items-start gap-2 px-3 py-2.5 rounded-lg cursor-pointer transition-colors slide-in-left stagger',
                        isActive
                          ? 'bg-accent/10 text-text-1'
                          : 'text-text-2 hover:bg-surface hover:text-text-1',
                      ].join(' ')
                    }
                  >
                    <div className="flex items-center gap-1.5 mt-[3px] shrink-0">
                      {statusDot(job.status)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs leading-snug truncate">{title}</p>
                      {job.submitted_at && (
                        <p className="text-[10px] text-text-3 mt-0.5">{relativeTime(job.submitted_at)}</p>
                      )}
                    </div>
                    <button
                      onClick={(e) => requestDelete(e, job.video_id)}
                      title="Delete"
                      className="opacity-30 md:opacity-0 group-hover:opacity-100 p-1.5 rounded text-text-3 hover:text-error active:text-error transition-all shrink-0 mt-0.5"
                    >
                      <Trash2 size={12} />
                    </button>
                  </NavLink>
                )
              })}
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center py-10 gap-2 text-center">
            <Clock size={18} className="text-text-3" />
            <p className="text-xs text-text-3">No videos yet.<br />Analyze your first video!</p>
          </div>
        )}
      </div>

      {/* PWA install prompt */}
      <InstallPrompt />

      {/* Bottom section: Library + API Key + Docs + user */}
      <div className="px-3 pt-2 border-t border-divider" style={{ paddingBottom: 'max(1rem, env(safe-area-inset-bottom))' }}>
        <div className="flex flex-col gap-0.5 mb-2">
          {bottomItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={handleNavClick}
              className={({ isActive }) =>
                [
                  'flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm transition-colors',
                  isActive
                    ? 'bg-accent/10 text-accent font-medium'
                    : 'text-text-2 hover:bg-surface hover:text-text-1',
                ].join(' ')
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </div>

        {/* Sync status */}
        <SyncStatus />

        {/* User info + logout */}
        <div className="pt-2 border-t border-divider/50">
          {user && (
            <div className="px-3 mb-2">
              <p className="text-xs font-medium text-text-1 truncate">
                {user.display_name ?? user.email}
              </p>
              <p className="text-xs text-text-3 truncate capitalize">{user.plan} plan</p>
            </div>
          )}
          <button
            onClick={() => setConfirmLogout(true)}
            className="flex items-center gap-2 text-xs text-text-3 hover:text-error transition-colors w-full px-3 py-2 rounded-lg hover:bg-surface"
          >
            <LogOut size={13} />
            Sign out
          </button>
        </div>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete chat?"
        message="This will permanently delete the video analysis and chat history. This cannot be undone."
        confirmLabel="Delete"
        variant="danger"
        loading={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
      <ConfirmDialog
        open={confirmLogout}
        title="Sign out?"
        message="You'll need to sign back in to access your chats and API key."
        confirmLabel="Sign out"
        cancelLabel="Stay"
        onConfirm={handleLogout}
        onCancel={() => setConfirmLogout(false)}
      />
    </aside>
  )
}
