import { useState, useRef, useEffect } from 'react'
import { Video, ArrowUp } from 'lucide-react'
import { useQuery as usePowerSyncQuery, useStatus } from '@powersync/react'
import { api } from '../../api/client'

interface ChatMsg {
  id: number
  role: 'user' | 'assistant'
  content: string
  loading?: boolean
}

let _id = 0
const uid = () => ++_id

const GREETING = "I've analysed this video. Ask me anything — what happens, who's in it, specific moments, mood, actions, you name it."

interface PlaygroundChatProps {
  videoId: string
}

// ---------------------------------------------------------------------------
// Minimal markdown → React renderer (no external deps)
// Handles: ## headings, **bold**, *italic*, - bullet lists, blank-line paragraphs
// ---------------------------------------------------------------------------
function MarkdownText({ text }: { text: string }) {
  const nodes: React.ReactNode[] = []
  const paragraphs = text.split(/\n{2,}/)

  paragraphs.forEach((para, pi) => {
    const lines = para.split('\n')

    // Bullet list block
    if (lines.every((l) => l.match(/^[-*]\s/))) {
      nodes.push(
        <ul key={pi} className="list-disc list-inside space-y-0.5 my-1">
          {lines.map((l, li) => (
            <li key={li} className="text-sm leading-relaxed">
              <InlineMarkdown text={l.replace(/^[-*]\s/, '')} />
            </li>
          ))}
        </ul>
      )
      return
    }

    // Mixed block — render line-by-line
    const renderedLines: React.ReactNode[] = []
    lines.forEach((line, li) => {
      // ## Heading
      const h2 = line.match(/^##\s+(.+)/)
      if (h2) {
        renderedLines.push(
          <p key={li} className="text-sm font-semibold text-text-1 mt-2 mb-0.5">
            <InlineMarkdown text={h2[1]} />
          </p>
        )
        return
      }
      // Bullet line mixed in a block
      const bullet = line.match(/^[-*]\s(.+)/)
      if (bullet) {
        renderedLines.push(
          <p key={li} className="text-sm leading-relaxed pl-3 before:content-['•'] before:mr-2 before:text-text-3">
            <InlineMarkdown text={bullet[1]} />
          </p>
        )
        return
      }
      // Normal line
      if (line.trim()) {
        renderedLines.push(
          <span key={li} className="text-sm leading-relaxed">
            <InlineMarkdown text={line} />
            {li < lines.length - 1 && lines[li + 1]?.trim() ? ' ' : ''}
          </span>
        )
      }
    })

    nodes.push(
      <p key={pi} className="text-sm leading-relaxed">
        {renderedLines}
      </p>
    )
  })

  return <div className="flex flex-col gap-1.5">{nodes}</div>
}

function InlineMarkdown({ text }: { text: string }) {
  // Split on **bold** and *italic*
  const parts: React.ReactNode[] = []
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*)/g
  let last = 0
  let m: RegExpExecArray | null

  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    const chunk = m[0]
    if (chunk.startsWith('**')) {
      parts.push(<strong key={m.index} className="font-semibold text-text-1">{chunk.slice(2, -2)}</strong>)
    } else {
      parts.push(<em key={m.index} className="italic">{chunk.slice(1, -1)}</em>)
    }
    last = m.index + chunk.length
  }
  if (last < text.length) parts.push(text.slice(last))
  return <>{parts}</>
}

// ---------------------------------------------------------------------------

const STORAGE_KEY = (videoId: string) => `vi_chat_${videoId}`

function loadMessages(videoId: string): ChatMsg[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY(videoId))
    if (raw) {
      const parsed = JSON.parse(raw) as ChatMsg[]
      if (Array.isArray(parsed) && parsed.length > 0) return parsed
    }
  } catch { /* ignore */ }
  return [{ id: uid(), role: 'assistant', content: GREETING }]
}

function saveMessages(videoId: string, msgs: ChatMsg[]) {
  try {
    // Don't persist loading placeholders
    const toSave = msgs.filter((m) => !m.loading)
    localStorage.setItem(STORAGE_KEY(videoId), JSON.stringify(toSave))
  } catch { /* ignore quota errors */ }
}

interface ChatMsgRow { id: string; role: string; content: string; created_at: string }

export function PlaygroundChat({ videoId }: PlaygroundChatProps) {
  const [messages, setMessages] = useState<ChatMsg[]>(() => loadMessages(videoId))
  const [input, setInput]   = useState('')
  const [busy, setBusy]     = useState(false)
  const bottomRef           = useRef<HTMLDivElement>(null)
  const textareaRef         = useRef<HTMLTextAreaElement>(null)
  const psStatus = useStatus()
  const hasSynced = psStatus?.hasSynced === true

  // PowerSync reactive chat history — updates in real-time across tabs/devices
  const { data: psMessages = [] } = usePowerSyncQuery<ChatMsgRow>(
    'SELECT id, role, content, created_at FROM chat_messages WHERE video_id = ? ORDER BY created_at ASC',
    [videoId]
  )

  // When PowerSync has synced, use its data (reactive, multi-device)
  useEffect(() => {
    if (!hasSynced) return
    if (psMessages.length > 0) {
      setMessages([
        { id: uid(), role: 'assistant', content: GREETING },
        ...psMessages.map((m) => ({
          id:   uid(),
          role: m.role as 'user' | 'assistant',
          content: m.content,
        })),
      ])
    } else {
      setMessages([{ id: uid(), role: 'assistant', content: GREETING }])
    }
  }, [hasSynced, videoId, psMessages.length])

  // Fallback: load chat history from REST API when PowerSync is not synced
  useEffect(() => {
    if (hasSynced) return
    setInput('')
    let cancelled = false
    api.getChatMessages(videoId).then((serverMsgs) => {
      if (cancelled) return
      if (serverMsgs && serverMsgs.length > 0) {
        setMessages([
          { id: uid(), role: 'assistant', content: GREETING },
          ...serverMsgs.map((m) => ({ id: uid(), role: m.role as 'user' | 'assistant', content: m.content })),
        ])
      } else {
        setMessages(loadMessages(videoId))
      }
    }).catch(() => {
      if (!cancelled) setMessages(loadMessages(videoId))
    })
    return () => { cancelled = true }
  }, [videoId, hasSynced])

  // Persist messages to localStorage as backup
  useEffect(() => {
    if (messages.some((m) => !m.loading)) {
      saveMessages(videoId, messages)
    }
  }, [videoId, messages])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async () => {
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'

    const userMsg: ChatMsg      = { id: uid(), role: 'user',      content: text }
    const placeholderId         = uid()
    const placeholder: ChatMsg  = { id: placeholderId, role: 'assistant', content: '', loading: true }

    setMessages((prev) => [...prev, userMsg, placeholder])
    setBusy(true)

    const history = messages
      .slice(1)
      .filter((m) => !m.loading)
      .map((m) => ({ role: m.role === 'assistant' ? 'model' : 'user', content: m.content }))

    try {
      const res = await api.chat(videoId, text, history)
      setMessages((prev) =>
        prev.map((m) => m.id === placeholderId ? { ...m, content: res.response, loading: false } : m)
      )
    } catch (e) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === placeholderId
            ? { ...m, content: `Error: ${e instanceof Error ? e.message : 'Request failed'}`, loading: false }
            : m
        )
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto flex flex-col gap-5 py-2 pr-1">
        {messages.map((msg, idx) => (
          <div
            key={msg.id}
            className={[
              msg.role === 'user' ? 'flex justify-end' : 'flex gap-2.5 items-start',
              'fade-up stagger',
            ].join(' ')}
            style={{ '--stagger': idx } as React.CSSProperties}
          >
            {msg.role === 'assistant' && (
              <div className="w-7 h-7 rounded-full bg-accent/10 flex items-center justify-center shrink-0 mt-0.5">
                <Video size={13} className="text-accent" />
              </div>
            )}
            <div
              className={[
                'rounded-2xl px-4 py-2.5 max-w-[88%]',
                msg.role === 'user'
                  ? 'bg-accent text-white text-sm rounded-tr-sm'
                  : 'bg-surface-2 border border-divider text-text-1 rounded-tl-sm',
              ].join(' ')}
            >
              {msg.loading ? (
                <span className="flex gap-1 items-center h-4">
                  <span className="w-1.5 h-1.5 bg-text-3 rounded-full animate-bounce [animation-delay:0ms]" />
                  <span className="w-1.5 h-1.5 bg-text-3 rounded-full animate-bounce [animation-delay:150ms]" />
                  <span className="w-1.5 h-1.5 bg-text-3 rounded-full animate-bounce [animation-delay:300ms]" />
                </span>
              ) : msg.role === 'assistant' ? (
                <MarkdownText text={msg.content} />
              ) : (
                <span className="text-sm whitespace-pre-wrap">{msg.content}</span>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 pt-3 pb-1">
        <div className="flex items-end gap-2 bg-surface border border-divider rounded-xl px-3 py-2 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20 transition-all">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            placeholder="Ask about the video…"
            disabled={busy}
            onChange={(e) => {
              setInput(e.target.value)
              e.target.style.height = 'auto'
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
            }}
            className="flex-1 resize-none bg-transparent text-sm text-text-1 placeholder:text-text-3 outline-none leading-relaxed min-h-[20px] max-h-32 overflow-y-auto disabled:opacity-50"
          />
          <button
            onClick={send}
            disabled={!input.trim() || busy}
            className="p-1.5 rounded-lg bg-accent text-white hover:bg-accent-dark disabled:opacity-30 disabled:cursor-not-allowed transition-colors shrink-0"
          >
            <ArrowUp size={14} />
          </button>
        </div>
        <p className="text-[11px] text-text-3 mt-1 text-center">Enter to send · Shift+Enter for new line</p>
      </div>
    </div>
  )
}
