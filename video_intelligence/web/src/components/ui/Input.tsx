import { type InputHTMLAttributes, forwardRef } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, className = '', id, ...rest }, ref) => {
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-')
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label htmlFor={inputId} className="text-sm font-medium text-text-1">
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={[
            'w-full rounded-lg border border-divider bg-surface px-3 py-2 text-sm text-text-1',
            'placeholder:text-text-3 outline-none',
            'focus:border-accent focus:ring-2 focus:ring-accent/20',
            'disabled:bg-surface-2 disabled:cursor-not-allowed',
            error ? 'border-error focus:border-error focus:ring-error/20' : '',
            className,
          ].join(' ')}
          {...rest}
        />
        {error && <p className="text-xs text-error">{error}</p>}
      </div>
    )
  }
)

Input.displayName = 'Input'
