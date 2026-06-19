type Status = 'queued' | 'processing' | 'complete' | 'failed' | 'active' | 'inactive'

const statusConfig: Record<Status, { dot: string; bg: string; text: string; label: string }> = {
  queued:     { dot: 'bg-info',    bg: 'bg-blue-50',  text: 'text-info',    label: 'Queued' },
  processing: { dot: 'bg-warning', bg: 'bg-amber-50', text: 'text-warning', label: 'Processing' },
  complete:   { dot: 'bg-success', bg: 'bg-green-50', text: 'text-success', label: 'Complete' },
  failed:     { dot: 'bg-error',   bg: 'bg-red-50',   text: 'text-error',   label: 'Failed' },
  active:     { dot: 'bg-success', bg: 'bg-green-50', text: 'text-success', label: 'Active' },
  inactive:   { dot: 'bg-text-3',  bg: 'bg-surface-2',text: 'text-text-2',  label: 'Inactive' },
}

interface BadgeProps {
  status: Status
  label?: string
  /** Renders a minimal dot-only badge for use in tight spaces like sidebars. */
  tiny?: boolean
}

export function Badge({ status, label, tiny }: BadgeProps) {
  const cfg = statusConfig[status]
  if (tiny) {
    return (
      <span className={['inline-flex items-center gap-1 text-[10px] font-medium', cfg.text].join(' ')}>
        <span className={['w-1.5 h-1.5 rounded-full shrink-0', cfg.dot].join(' ')} />
        {label ?? cfg.label}
      </span>
    )
  }
  return (
    <span
      className={[
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium',
        cfg.bg,
        cfg.text,
      ].join(' ')}
    >
      <span className={['w-1.5 h-1.5 rounded-full shrink-0', cfg.dot].join(' ')} />
      {label ?? cfg.label}
    </span>
  )
}
