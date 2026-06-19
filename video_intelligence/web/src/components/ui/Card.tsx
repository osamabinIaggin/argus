import { type ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
  padding?: boolean
}

export function Card({ children, className = '', padding = true }: CardProps) {
  return (
    <div
      className={[
        'bg-surface rounded-xl border border-divider shadow-sm transition-shadow duration-150',
        padding ? 'p-5' : '',
        className,
      ].join(' ')}
    >
      {children}
    </div>
  )
}
