import { Check, Zap, Bell, BellOff } from 'lucide-react'
import { ProgressBar } from '../ui/ProgressBar'
import { useNotifications } from '../../hooks/useNotifications'
import type { StatusResponse } from '../../types'

const STAGES = [
  { key: 'preprocessing',       label: 'Preprocessing',       emoji: '🎬' },
  { key: 'extracting_keyframes', label: 'Extracting keyframes', emoji: '🖼' },
  { key: 'yolo_analysis',        label: 'Object detection',     emoji: '🔍' },
  { key: 'audio_analysis',       label: 'Audio analysis',       emoji: '🎙' },
  { key: 'vision_model',         label: 'Vision model',         emoji: '🧠' },
  { key: 'stitching',            label: 'Stitching results',    emoji: '✨' },
]

const THRESHOLDS = [5, 20, 40, 55, 90, 98]

function stageStatus(
  idx: number,
  progressPct: number,
  currentStage?: string
): 'done' | 'running' | 'waiting' {
  if (STAGES[idx]?.key === currentStage) return 'running'
  if (progressPct >= (THRESHOLDS[idx] ?? 100)) return 'done'
  return 'waiting'
}

interface PipelineProgressProps {
  videoId: string
  status: StatusResponse
}

export function PipelineProgress({ videoId, status }: PipelineProgressProps) {
  const isDone   = status.status === 'complete'
  const isFailed = status.status === 'failed'
  const isRunning = !isDone && !isFailed
  const { state: notifState, requestPermission } = useNotifications()

  return (
    <div className="flex flex-col gap-6 fade-up">
      {/* Progress header */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-text-1">
            {isDone ? 'Complete!' : isFailed ? 'Failed' : 'Processing…'}
          </span>
          <span className="text-sm font-semibold text-accent tabular-nums">
            {status.progress_percent}%
          </span>
        </div>
        <ProgressBar value={status.progress_percent} animated={!isDone && !isFailed} />
        <p className="text-xs text-text-3 font-mono truncate">{videoId}</p>
      </div>

      {/* Stage steps */}
      <div className="flex flex-col gap-1">
        {STAGES.map((stage, i) => {
          const s = isDone
            ? 'done'
            : isFailed
            ? i === 0 ? 'done' : 'waiting'
            : stageStatus(i, status.progress_percent, status.current_stage)

          return (
            <div
              key={stage.key}
              style={{ '--stagger': i } as React.CSSProperties}
              className={[
                'flex items-center gap-3 px-3 py-2 rounded-lg transition-colors stagger fade-in',
                s === 'running' ? 'bg-accent/8 border border-accent/20' : '',
                s === 'done'    ? 'opacity-50'                          : '',
              ].join(' ')}
            >
              {/* Icon */}
              <div className={[
                'w-6 h-6 rounded-full flex items-center justify-center text-xs shrink-0',
                s === 'done'    ? 'bg-success/15 text-success' :
                s === 'running' ? 'bg-accent/15 text-accent'   :
                                  'bg-surface-2 text-text-3',
              ].join(' ')}>
                {s === 'done'    ? <Check size={11} strokeWidth={2.5} /> :
                 s === 'running' ? <Zap size={11} className="animate-pulse" /> :
                                   <span className="opacity-50">{stage.emoji}</span>}
              </div>

              <span className={[
                'text-sm flex-1',
                s === 'running' ? 'text-text-1 font-medium' :
                s === 'done'    ? 'text-text-3 line-through' :
                                  'text-text-3',
              ].join(' ')}>
                {stage.label}
              </span>

              {s === 'running' && (
                <span className="text-[10px] font-medium text-accent animate-pulse">
                  running
                </span>
              )}
              {s === 'done' && (
                <Check size={11} className="text-success shrink-0" />
              )}
            </div>
          )
        })}
      </div>

      {isFailed && (
        <div className="rounded-lg bg-error/8 border border-error/20 px-4 py-3 text-sm text-error fade-in">
          {status.error ?? 'Processing failed. Please try again.'}
        </div>
      )}

      {/* Notification opt-in — shown while job is running */}
      {isRunning && notifState === 'idle' && (
        <button
          onClick={requestPermission}
          className="flex items-center gap-2 w-full px-4 py-3 rounded-lg border border-dashed border-divider text-sm text-text-2 hover:border-accent/40 hover:text-accent hover:bg-accent/5 transition-all fade-in"
        >
          <Bell size={14} className="shrink-0" />
          Notify me when done — leave this page safely
        </button>
      )}
      {isRunning && notifState === 'loading' && (
        <div className="flex items-center gap-2 px-4 py-3 text-sm text-text-3 fade-in">
          <Bell size={14} className="animate-pulse shrink-0" />
          Enabling notifications…
        </div>
      )}
      {isRunning && notifState === 'granted' && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-lg bg-success/8 border border-success/20 text-sm text-success fade-in">
          <Bell size={14} className="shrink-0" />
          You'll get a notification when this finishes
        </div>
      )}
      {isRunning && notifState === 'denied' && (
        <div className="flex items-center gap-2 px-4 py-3 text-sm text-text-3 fade-in">
          <BellOff size={14} className="shrink-0" />
          Notifications blocked — enable them in browser settings
        </div>
      )}
    </div>
  )
}
