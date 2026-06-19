import { useState } from 'react'
import { Check, Copy } from 'lucide-react'

interface CopyButtonProps {
  text: string
  size?: number
  className?: string
}

export function CopyButton({ text, size = 14, className = '' }: CopyButtonProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      /* clipboard not available */
    }
  }

  return (
    <button
      onClick={handleCopy}
      title="Copy to clipboard"
      className={[
        'inline-flex items-center justify-center rounded p-1 transition-colors',
        'text-text-3 hover:text-text-1 hover:bg-surface-2',
        className,
      ].join(' ')}
    >
      {copied ? (
        <Check size={size} className="text-success" />
      ) : (
        <Copy size={size} />
      )}
    </button>
  )
}
