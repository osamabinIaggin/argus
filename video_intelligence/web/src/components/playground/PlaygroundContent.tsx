import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useLocalStorage } from '../../hooks/useLocalStorage'
import { Play, Download, Link as LinkIcon, Loader2, AlertCircle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import { useJobStatus } from '../../hooks/useJobStatus'
import { useApiKey } from '../../context/ApiKeyContext'
import { VideoDropzone } from './VideoDropzone'
import { UrlInput } from './UrlInput'
import { PipelineProgress } from './PipelineProgress'
import { PlaygroundChat } from './PlaygroundChat'
import { TimelineView } from '../results/TimelineView'
import { JsonViewer } from '../results/JsonViewer'
import { Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { CopyButton } from '../ui/CopyButton'
import type { VideoResult } from '../../types'

type InputMode = 'file' | 'url'
type ResultTab = 'timeline' | 'json' | 'chat'
const FPS_OPTIONS = [1, 2, 5, 10]

function buildCurlSnippet(videoId: string): string {
  const origin = window.location.origin
  return `# 1. Poll status
curl -H "Authorization: Bearer $API_KEY" \\
  ${origin}/v1/status/${videoId}

# 2. Fetch result
curl -H "Authorization: Bearer $API_KEY" \\
  ${origin}/v1/result/${videoId}`
}

function buildPythonSnippet(fps: number): string {
  const origin = window.location.origin
  return `import requests, time

API_KEY = "vi_live_..."
BASE    = "${origin}/v1"
headers = {"Authorization": f"Bearer {API_KEY}"}

r = requests.post(f"{BASE}/analyze",
    headers=headers,
    files={"file": open("video.mp4", "rb")},
    data={"fps": ${fps}})
vid = r.json()["video_id"]

while True:
    s = requests.get(f"{BASE}/status/{vid}", headers=headers).json()
    if s["status"] == "complete": break
    time.sleep(2)

result = requests.get(f"{BASE}/result/{vid}", headers=headers).json()`
}

// ---------------------------------------------------------------------------
// Result panel — shown once a job is complete
// ---------------------------------------------------------------------------

function ResultPanel({ result, videoId }: { result: VideoResult; videoId: string }) {
  const [tab, setTab] = useLocalStorage<ResultTab>(`vi_pg_tab_${videoId}`, 'timeline')

  const downloadJson = () => {
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${result.video_id}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const TABS: { key: ResultTab; label: string }[] = [
    { key: 'timeline', label: 'Timeline' },
    { key: 'json', label: 'JSON' },
    { key: 'chat', label: '💬 Chat' },
  ]

  return (
    <Card padding={false} className="flex flex-col overflow-hidden">
      {/* Metadata header */}
      <div className="px-4 py-3 border-b border-divider flex flex-wrap items-center gap-x-4 gap-y-1">
        <div className="flex gap-3 text-xs text-text-2 flex-1 flex-wrap">
          <span className="text-success font-medium">✓ Complete</span>
          <span className="text-text-3">·</span>
          <span>{result.metadata?.duration_seconds?.toFixed(1) ?? '?'}s</span>
          <span className="text-text-3">·</span>
          <span>{result.metadata?.processed_resolution ?? 'unknown'}</span>
          <span className="text-text-3">·</span>
          <span>{result.metadata?.keyframes_analyzed ?? '?'} keyframes</span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={downloadJson}
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs text-text-2 hover:text-text-1 hover:bg-surface-2 transition-colors border border-divider"
          >
            <Download size={12} />
            JSON
          </button>
          <Link to={`/jobs/${videoId}`}>
            <button className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs text-text-2 hover:text-text-1 hover:bg-surface-2 transition-colors border border-divider">
              <LinkIcon size={12} />
              Full view
            </button>
          </Link>
        </div>
      </div>

      {/* Summary */}
      <div className="px-4 py-3 border-b border-divider bg-surface-2">
        <p className="text-xs text-text-1 leading-relaxed line-clamp-3">{result.summary}</p>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-divider bg-surface">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={[
              'px-4 py-2.5 text-xs font-medium transition-colors border-b-2 -mb-px',
              tab === key
                ? 'border-accent text-accent'
                : 'border-transparent text-text-2 hover:text-text-1',
            ].join(' ')}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div
        className={[
          'overflow-y-auto',
          tab === 'chat' ? 'flex flex-col flex-1 px-4 min-h-[420px]' : 'p-4 max-h-[520px]',
        ].join(' ')}
      >
        {tab === 'timeline' && <TimelineView timeline={result.timeline} />}
        {tab === 'json' && <JsonViewer data={result} />}
        {tab === 'chat' && <PlaygroundChat videoId={videoId} />}
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Shared playground content — used by both TryPage and Playground
// ---------------------------------------------------------------------------

export interface PlaygroundContentProps {
  /** When true, show key banner and prompt GetKeyModal on analyze if no key */
  requireKeyPrompt?: boolean
  /** Called when user tries to analyze without a key — show modal */
  onKeyRequired?: () => void
  /** Optional title override */
  title?: string
}

export function PlaygroundContent({
  requireKeyPrompt = false,
  onKeyRequired,
  title = 'Playground',
}: PlaygroundContentProps) {
  const { apiKey } = useApiKey()
  const [inputMode, setInputMode] = useState<InputMode>('file')
  const [fps, setFps] = useLocalStorage<number>('vi_pg_fps', 5)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [videoId, setVideoId] = useLocalStorage<string | null>('vi_pg_video_id', null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [snippetLang, setSnippetLang] = useLocalStorage<'curl' | 'python'>('vi_pg_snippet_lang', 'curl')

  const { data: status, isLoading: isLoadingStatus, isError: isStatusError } = useJobStatus(videoId)

  const { data: result } = useQuery<VideoResult>({
    queryKey: ['result', videoId],
    queryFn: () => api.getResult(videoId!),
    enabled: !!videoId && status?.status === 'complete',
    staleTime: Infinity,
  })

  const needsKey = requireKeyPrompt && !apiKey

  const handleAnalyze = async () => {
    if (!selectedFile) return
    if (needsKey && onKeyRequired) {
      onKeyRequired()
      return
    }
    setSubmitError('')
    setSubmitting(true)
    try {
      const res = await api.analyzeFile(selectedFile, fps)
      setVideoId(res.video_id)
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : 'Submission failed')
    } finally {
      setSubmitting(false)
    }
  }

  const handleUrl = async (url: string) => {
    if (needsKey && onKeyRequired) {
      onKeyRequired()
      return
    }
    setSubmitError('')
    setSubmitting(true)
    try {
      const res = await api.analyzeUrl(url, fps)
      setVideoId(res.video_id)
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : 'Submission failed')
    } finally {
      setSubmitting(false)
    }
  }

  const reset = () => {
    if (videoId) localStorage.removeItem(`vi_pg_tab_${videoId}`)
    setVideoId(null)
    setSelectedFile(null)
    setSubmitError('')
  }

  const isComplete = !!result && status?.status === 'complete'

  return (
    <div className="flex flex-col gap-6">
      {needsKey && (
        <div className="flex items-center justify-between gap-4 p-4 rounded-xl bg-accent/10 border border-accent/20">
          <p className="text-sm text-text-1">
            Get a free API key to analyze videos. No credit card required.
          </p>
          <Button size="sm" onClick={onKeyRequired}>
            Get API Key
          </Button>
        </div>
      )}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-text-1">{title}</h1>
      </div>

      <div className="grid lg:grid-cols-2 gap-6 items-start">
        {/* ---- Left panel: input + code snippet ---- */}
        <div className="flex flex-col gap-4">
          <Card>
            {videoId ? (
              <div className="flex flex-col gap-4">
                <div className="flex items-start gap-3 p-3 bg-surface-2 rounded-lg border border-divider">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-text-3 mb-0.5">Job submitted</p>
                    <p className="font-mono text-xs text-accent truncate">{videoId}</p>
                    {selectedFile && (
                      <p className="text-xs text-text-3 mt-1 truncate">{selectedFile.name}</p>
                    )}
                  </div>
                </div>
                <Button variant="secondary" className="w-full" onClick={reset}>
                  ← Analyze another video
                </Button>
              </div>
            ) : (
              <>
                {/* File / URL toggle */}
                <div className="flex gap-1 mb-5 bg-surface-2 rounded-lg p-1 w-fit">
                  {(['file', 'url'] as InputMode[]).map((m) => (
                    <button
                      key={m}
                      onClick={() => setInputMode(m)}
                      className={[
                        'px-4 py-1.5 rounded-md text-sm font-medium transition-colors',
                        inputMode === m
                          ? 'bg-surface text-text-1 shadow-sm'
                          : 'text-text-2 hover:text-text-1',
                      ].join(' ')}
                    >
                      {m === 'file' ? 'Upload file' : 'Paste URL'}
                    </button>
                  ))}
                </div>

                {inputMode === 'file' ? (
                  selectedFile ? (
                    <div className="flex items-center gap-3 p-3 bg-surface-2 rounded-lg border border-divider">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-text-1 truncate">{selectedFile.name}</p>
                        <p className="text-xs text-text-3">{(selectedFile.size / 1024 / 1024).toFixed(1)} MB</p>
                      </div>
                      <button onClick={() => setSelectedFile(null)} className="text-text-3 hover:text-text-1 text-xs shrink-0">✕</button>
                    </div>
                  ) : (
                    <VideoDropzone onFile={setSelectedFile} />
                  )
                ) : (
                  <UrlInput onSubmit={handleUrl} loading={submitting} />
                )}

                {/* FPS */}
                <div className="mt-5 flex items-center gap-3">
                  <span className="text-sm text-text-2">FPS:</span>
                  <div className="flex gap-1">
                    {FPS_OPTIONS.map((f) => (
                      <button
                        key={f}
                        onClick={() => setFps(f)}
                        className={[
                          'w-9 h-8 rounded-lg text-sm font-medium transition-colors',
                          fps === f ? 'bg-accent text-white' : 'bg-surface-2 text-text-2 hover:bg-surface hover:text-text-1',
                        ].join(' ')}
                      >
                        {f}
                      </button>
                    ))}
                  </div>
                </div>

                {submitError && <p className="mt-3 text-sm text-error">{submitError}</p>}

                {inputMode === 'file' && (
                  <Button className="w-full mt-5" onClick={handleAnalyze} loading={submitting} disabled={!selectedFile}>
                    <Play size={16} />
                    Analyze
                  </Button>
                )}
              </>
            )}
          </Card>

          {/* Code snippet — only after job starts */}
          {videoId && (
            <Card padding={false}>
              <div className="flex items-center justify-between px-4 py-3 border-b border-divider">
                <div className="flex gap-1 bg-surface-2 rounded p-0.5">
                  {(['curl', 'python'] as const).map((lang) => (
                    <button
                      key={lang}
                      onClick={() => setSnippetLang(lang)}
                      className={[
                        'px-3 py-1 text-xs font-medium rounded transition-colors',
                        snippetLang === lang ? 'bg-surface text-text-1 shadow-sm' : 'text-text-2 hover:text-text-1',
                      ].join(' ')}
                    >
                      {lang === 'curl' ? 'cURL' : 'Python'}
                    </button>
                  ))}
                </div>
                <CopyButton text={snippetLang === 'curl' ? buildCurlSnippet(videoId) : buildPythonSnippet(fps)} />
              </div>
              <pre className="p-4 text-xs font-mono text-text-2 overflow-auto whitespace-pre-wrap">
                {snippetLang === 'curl' ? buildCurlSnippet(videoId) : buildPythonSnippet(fps)}
              </pre>
            </Card>
          )}
        </div>

        {/* ---- Right panel: loading → progress → result ---- */}
        <div>
          {!videoId ? (
            <div className="h-64 flex flex-col items-center justify-center gap-3 border-2 border-dashed border-divider rounded-xl text-text-3 text-sm transition-colors hover:border-accent/30 hover:text-text-2">
              <Loader2 size={20} className="opacity-30" />
              Results appear here after analysis starts.
            </div>
          ) : isStatusError ? (
            <Card className="fade-up">
              <div className="flex flex-col items-center gap-4 py-6 text-center">
                <AlertCircle size={32} className="text-error" />
                <div>
                  <p className="text-sm font-medium text-text-1">Job not found</p>
                  <p className="text-xs text-text-3 mt-1">
                    This job may have been deleted or expired.
                  </p>
                </div>
                <Button variant="secondary" size="sm" onClick={reset}>
                  Start a new analysis
                </Button>
              </div>
            </Card>
          ) : isLoadingStatus || !status ? (
            <Card className="fade-in">
              <div className="flex items-center justify-center gap-3 py-10 text-text-3 text-sm">
                <Loader2 size={18} className="animate-spin" />
                Loading job status…
              </div>
            </Card>
          ) : isComplete && result ? (
            <div className="scale-in">
              <ResultPanel result={result} videoId={videoId} />
            </div>
          ) : (
            <Card className="fade-in">
              <PipelineProgress videoId={videoId} status={status} />
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
