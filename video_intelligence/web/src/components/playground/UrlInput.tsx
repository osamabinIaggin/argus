import { useState } from 'react'
import { Link2 } from 'lucide-react'
import { Button } from '../ui/Button'

interface UrlInputProps {
  onSubmit: (url: string) => void
  loading?: boolean
}

export function UrlInput({ onSubmit, loading }: UrlInputProps) {
  const [url, setUrl] = useState('')

  const handleSubmit = () => {
    const trimmed = url.trim()
    if (trimmed) onSubmit(trimmed)
  }

  return (
    <div className="flex gap-2">
      <div className="flex-1 relative">
        <Link2 size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-3" />
        <input
          type="url"
          placeholder="https://example.com/video.mp4"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
          className="w-full rounded-lg border border-divider bg-surface pl-8 pr-3 py-2 text-sm text-text-1 placeholder:text-text-3 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
        />
      </div>
      <Button size="sm" onClick={handleSubmit} loading={loading} disabled={!url.trim()}>
        Fetch
      </Button>
    </div>
  )
}
