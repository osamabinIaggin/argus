import { Download } from 'lucide-react'
import { Button } from '../ui/Button'
import type { VideoResult } from '../../types'

type ResultTab = 'timeline' | 'json' | 'chat'

interface MetadataBarProps {
  result: VideoResult
  activeTab: ResultTab
  onTabChange: (tab: ResultTab) => void
}

export function MetadataBar({ result, activeTab, onTabChange }: MetadataBarProps) {
  const { metadata, video_id } = result

  const handleDownload = () => {
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${video_id}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="bg-surface border border-divider rounded-xl p-4 flex flex-col sm:flex-row sm:items-center gap-4">
      <div className="flex-1 flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <span className="font-mono text-xs text-text-2">{video_id}</span>
        <span className="text-text-3">·</span>
        <span className="text-text-2">{metadata?.duration_seconds?.toFixed(1) ?? '?'}s</span>
        <span className="text-text-3">·</span>
        <span className="text-text-2">{metadata?.processed_resolution ?? 'unknown'}</span>
        <span className="text-text-3">·</span>
        <span className="text-text-2">{metadata?.keyframes_analyzed ?? '?'} keyframes</span>
      </div>

      <div className="flex items-center gap-3">
        {/* Tabs */}
        <div className="flex gap-1 bg-surface-2 rounded-lg p-1">
          {(['timeline', 'json', 'chat'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => onTabChange(tab)}
              className={[
                'px-3 py-1.5 rounded text-xs font-medium transition-colors',
                activeTab === tab
                  ? 'bg-surface text-text-1 shadow-sm'
                  : 'text-text-2 hover:text-text-1',
              ].join(' ')}
            >
              {tab === 'chat' ? '💬 Chat' : tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>

        <Button variant="secondary" size="sm" onClick={handleDownload}>
          <Download size={13} />
          JSON
        </Button>
      </div>
    </div>
  )
}
