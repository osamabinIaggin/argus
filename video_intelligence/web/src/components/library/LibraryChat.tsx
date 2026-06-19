import { useState, useRef, useEffect } from 'react'
import { useQuery as usePowerSyncQuery, useStatus } from '@powersync/react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Send, Library, Loader2 } from 'lucide-react'
import { api } from '../../api/client'

// Simple inline markdown renderer (bold + italic) — no external deps
function InlineMarkdown({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g)
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith('**') && p.endsWith('**'))
          return <strong key={i}>{p.slice(2, -2)}</strong>
        if (p.startsWith('*') && p.endsWith('*'))
          return <em key={i}>{p.slice(1, -1)}</em>
        return p
      })}
    </>
  )
}

function MarkdownText({ text }: { text: string }) {
  const paragraphs = text.split(/\n{2,}/)
  return (
    <div className="space-y-2">
      {paragraphs.map((para, pi) => {
        const lines = para.split('\n')
        if (lines.every((l) => l.match(/^[-*]\s/))) {
          return (
            <ul key={pi} className="list-disc list-inside space-y-0.5">
              {lines.map((l, li) => (
                <li key={li} className="text-sm leading-relaxed">
                  <InlineMarkdown text={l.replace(/^[-*]\s/, '')} />
                </li>
              ))}
            </ul>
          )
        }
        return (
          <p key={pi} className="text-sm leading-relaxed">
            {lines.map((line, li) => {
              const h2 = line.match(/^##\s+(.+)/)
              if (h2) return <strong key={li} className="block mt-1"><InlineMarkdown text={h2[1]} /></strong>
              return <span key={li}><InlineMarkdown text={line} />{li < lines.length - 1 && ' '}</span>
            })}
          </p>
        )
      })}
    </div>
  )
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
}

/**
 * Cross-video library chat powered by Mastra + PowerSync.
 *
 * When PowerSync is synced: reads history from local SQLite — instant,
 * reactive, multi-device.  Falls back to REST when not synced.
 */
export default function LibraryChat() {
  const [input, setInput]   = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError]   = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()
  const psStatus = useStatus()
  const hasSynced = psStatus?.hasSynced === true

  // PowerSync reactive query on library_messages
  const { data: psRows = [] } = usePowerSyncQuery<Message>(
    `SELECT id, role, content FROM library_messages ORDER BY created_at ASC`
  )

  // REST fallback
  const { data: restMessages = [] } = useQuery<Message[]>({
    queryKey: ['library-messages'],
    queryFn:  () => api.getLibraryMessages() as Promise<Message[]>,
    enabled:  !hasSynced,
    staleTime: 60_000,
  })

  const messages: Message[] = hasSynced ? psRows : restMessages

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  const handleSend = async () => {
    const msg = input.trim()
    if (!msg || sending) return
    setInput('')
    setSending(true)
    setError(null)
    try {
      await api.libraryChat(msg)
      // PowerSync will auto-update psRows. In fallback mode, invalidate cache.
      if (!hasSynced) {
        queryClient.invalidateQueries({ queryKey: ['library-messages'] })
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-divider shrink-0">
        <div className="flex items-center gap-2">
          <Library size={18} className="text-accent" />
          <h1 className="font-semibold text-text-1">Video Library</h1>
        </div>
        <p className="text-xs text-text-3 mt-1">
          Ask questions across all your analysed videos at once.
        </p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center py-16">
            <Library size={32} className="text-text-3" />
            <p className="text-sm font-medium text-text-1">Cross-video intelligence</p>
            <p className="text-xs text-text-3 max-w-xs">
              Ask anything about your entire video collection. Find scenes, compare videos,
              spot recurring patterns.
            </p>
            <div className="mt-2 flex flex-col gap-2 items-center">
              {[
                'What videos have people in them?',
                'Find all scenes with cars',
                'Summarise my workout videos',
              ].map((s) => (
                <button
                  key={s}
                  onClick={() => setInput(s)}
                  className="text-xs px-3 py-1.5 rounded-full border border-divider text-text-2 hover:border-accent hover:text-accent transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={[
                'max-w-[80%] rounded-2xl px-4 py-3 text-sm',
                m.role === 'user'
                  ? 'bg-accent text-white rounded-br-sm'
                  : 'bg-surface-2 text-text-1 rounded-bl-sm',
              ].join(' ')}
            >
              {m.role === 'assistant' ? (
                <MarkdownText text={m.content} />
              ) : (
                m.content
              )}
            </div>
          </div>
        ))}

        {sending && (
          <div className="flex justify-start">
            <div className="bg-surface-2 rounded-2xl rounded-bl-sm px-4 py-3">
              <Loader2 size={16} className="text-text-3 animate-spin" />
            </div>
          </div>
        )}

        {error && (
          <p className="text-xs text-error text-center">{error}</p>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-4 py-4 border-t border-divider shrink-0">
        <form
          onSubmit={(e) => { e.preventDefault(); handleSend() }}
          className="flex items-end gap-2"
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
            }}
            placeholder="Ask about your entire video library…"
            rows={1}
            className="flex-1 resize-none rounded-xl border border-divider bg-surface px-4 py-3 text-sm text-text-1 placeholder-text-3 focus:outline-none focus:border-accent transition-colors min-h-[44px] max-h-32"
            style={{ field_sizing: 'content' } as React.CSSProperties}
            disabled={sending}
          />
          <button
            type="submit"
            disabled={!input.trim() || sending}
            className="p-3 rounded-xl bg-accent text-white disabled:opacity-40 hover:bg-accent/90 transition-colors shrink-0"
          >
            {sending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </form>
      </div>
    </div>
  )
}
