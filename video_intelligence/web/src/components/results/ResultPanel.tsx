/**
 * ResultPanel — the right-hand pane in the Jobs split layout.
 *
 * Shows the chat view by default. Users can switch to Timeline or JSON
 * via the tab bar in the header.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, Loader2 } from 'lucide-react'
import { api } from '../../api/client'
import { useJobStatus } from '../../hooks/useJobStatus'
import { SummaryCard } from './SummaryCard'
import { TimelineView } from './TimelineView'
import { JsonViewer } from './JsonViewer'
import { PlaygroundChat } from '../playground/PlaygroundChat'
import { PipelineProgress } from '../playground/PipelineProgress'
import { Button } from '../ui/Button'
import { Badge } from '../ui/Badge'
import type { VideoResult } from '../../types'

type ResultTab = 'chat' | 'timeline' | 'json'

interface ResultPanelProps {
  videoId: string
}

export function ResultPanel({ videoId }: ResultPanelProps) {
  const [tab, setTab] = useState<ResultTab>('chat')
  const { data: status } = useJobStatus(videoId, true)

  const { data: result, isLoading } = useQuery<VideoResult>({
    queryKey: ['result', videoId],
    queryFn: () => api.getResult(videoId),
    enabled: !!videoId && status?.status === 'complete',
    staleTime: Infinity,
  })

  const handleDownload = () => {
    if (!result) return
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${videoId}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  // ── Still processing ──────────────────────────────────────────────────────
  if (status && status.status !== 'complete' && status.status !== 'failed') {
    return (
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header videoId={videoId} status={status.status} />
        <div className="flex-1 overflow-auto p-6">
          <PipelineProgress videoId={videoId} status={status} />
        </div>
      </div>
    )
  }

  // ── Failed ────────────────────────────────────────────────────────────────
  if (status?.status === 'failed') {
    return (
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header videoId={videoId} status="failed" />
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm text-error">{status.error ?? 'Processing failed.'}</p>
        </div>
      </div>
    )
  }

  // ── Loading result ────────────────────────────────────────────────────────
  if (isLoading || !result) {
    return (
      <div className="flex-1 flex items-center justify-center gap-2 text-text-3">
        <Loader2 size={18} className="animate-spin" />
        <span className="text-sm">Loading…</span>
      </div>
    )
  }

  // ── Complete ──────────────────────────────────────────────────────────────
  return (
    <div className="flex-1 flex flex-col overflow-hidden fade-in">
      {/* Top bar: video id + tabs + download */}
      <div className="shrink-0 h-14 px-5 flex items-center justify-between border-b border-divider gap-4">
        <div className="flex items-center gap-2.5 min-w-0">
          <Badge status="complete" tiny />
          <span className="font-mono text-xs text-text-2 truncate">{videoId}</span>
          <span className="text-text-3 text-xs hidden sm:inline">
            · {result.metadata?.duration_seconds?.toFixed(1) ?? '?'}s
            · {result.metadata?.keyframes_analyzed ?? '?'} keyframes
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div className="flex gap-0.5 bg-surface-2 rounded-lg p-0.5">
            {(['chat', 'timeline', 'json'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={[
                  'px-3 py-1.5 rounded text-xs font-medium transition-colors',
                  tab === t ? 'bg-surface text-text-1 shadow-sm' : 'text-text-2 hover:text-text-1',
                ].join(' ')}
              >
                {t === 'chat' ? 'Chat' : t === 'timeline' ? 'Timeline' : 'JSON'}
              </button>
            ))}
          </div>
          <Button variant="secondary" size="sm" onClick={handleDownload}>
            <Download size={13} />
          </Button>
        </div>
      </div>

      {/* Content */}
      <div className={`flex-1 overflow-hidden flex flex-col ${tab !== 'chat' ? 'overflow-y-auto' : ''}`}>
        {tab === 'chat' && (
          <div className="flex-1 flex flex-col overflow-hidden px-6 pt-4 pb-2">
            {result.summary && (
              <p className="text-xs text-text-3 border-b border-divider pb-3 mb-3 line-clamp-2">
                {result.summary}
              </p>
            )}
            <PlaygroundChat videoId={videoId} />
          </div>
        )}
        {tab === 'timeline' && (
          <div className="overflow-y-auto p-6 flex flex-col gap-4">
            <SummaryCard summary={result.summary} />
            <TimelineView timeline={result.timeline} />
          </div>
        )}
        {tab === 'json' && (
          <div className="overflow-y-auto p-6">
            <JsonViewer data={result} />
          </div>
        )}
      </div>
    </div>
  )
}

function Header({ videoId, status }: { videoId: string; status: string }) {
  return (
    <div className="shrink-0 h-14 px-5 flex items-center gap-2.5 border-b border-divider">
      <Badge status={status as any} tiny />
      <span className="font-mono text-xs text-text-2">{videoId}</span>
    </div>
  )
}
