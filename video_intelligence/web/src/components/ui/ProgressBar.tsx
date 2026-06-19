interface ProgressBarProps {
  value: number   // 0–100
  animated?: boolean
  className?: string
}

export function ProgressBar({ value, animated = false, className = '' }: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, value))
  return (
    <div className={['h-1 w-full bg-surface-2 rounded-full overflow-hidden', className].join(' ')}>
      <div
        className={[
          'h-full rounded-full transition-all duration-500',
          animated && pct < 100 ? 'shimmer' : 'bg-accent',
        ].join(' ')}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}
