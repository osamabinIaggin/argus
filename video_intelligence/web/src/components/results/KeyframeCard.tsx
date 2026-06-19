import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import type { KeyframeEntry } from '../../types'

interface KeyframeCardProps {
  entry: KeyframeEntry
  isSceneStart: boolean
}

export function KeyframeCard({ entry, isSceneStart }: KeyframeCardProps) {
  const [expanded, setExpanded] = useState(false)

  const hasExtras =
    !!entry.changes_from_previous ||
    !!entry.actions ||
    entry.detected_objects.length > 0

  return (
    <div className="relative">
      {/* Scene-change separator */}
      {isSceneStart && entry.keyframe_id > 1 && (
        <div className="flex items-center gap-3 my-3 text-xs text-text-3 font-medium">
          <div className="flex-1 h-px bg-accent/30" />
          <span className="px-2 py-0.5 bg-accent/10 text-accent rounded-full text-[10px] tracking-wide">
            SCENE CHANGE
          </span>
          <div className="flex-1 h-px bg-accent/30" />
        </div>
      )}

      <div
        className={[
          'bg-surface border rounded-xl transition-all duration-200 group card-hover',
          isSceneStart ? 'border-l-2 border-l-accent border-accent/30' : 'border-divider',
          hasExtras ? 'cursor-pointer hover:border-text-3' : '',
        ].join(' ')}
        onClick={() => hasExtras && setExpanded((v) => !v)}
      >
        {/* Always-visible header row */}
        <div className="flex items-center gap-3 px-4 pt-3.5 pb-1 flex-wrap">
          <span className="bg-surface-2 text-text-2 text-xs font-mono px-2 py-0.5 rounded shrink-0">
            {entry.timestamp_start} → {entry.timestamp_end}
          </span>

          {isSceneStart ? (
            <span className="flex items-center gap-1 text-xs text-accent shrink-0">
              <span className="w-1.5 h-1.5 rounded-full bg-accent" />
              scene change
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs text-text-3 shrink-0">
              <span className="w-1.5 h-1.5 rounded-full bg-text-3" />
              same scene
            </span>
          )}

          {entry.confidence > 0 && (
            <span className="text-xs text-text-3 ml-auto shrink-0">
              conf: {entry.confidence.toFixed(2)}
            </span>
          )}

          {hasExtras && (
            <ChevronDown
              size={14}
              className={[
                'text-text-3 transition-transform ml-auto shrink-0',
                expanded ? 'rotate-180' : '',
                entry.confidence > 0 ? 'ml-1' : '',
              ].join(' ')}
            />
          )}
        </div>

        {/* Description — always shown */}
        <p className="px-4 pb-3.5 text-sm text-text-1 leading-relaxed">{entry.description}</p>

        {/* Expanded detail panel */}
        <div
          className={[
            'border-t border-divider px-4 flex flex-col gap-2.5 bg-surface-2 rounded-b-xl transition-all duration-200 overflow-hidden',
            expanded && hasExtras ? 'max-h-96 py-3 opacity-100' : 'max-h-0 py-0 opacity-0 border-t-transparent',
          ].join(' ')}
          onClick={(e) => e.stopPropagation()}
        >
            {entry.changes_from_previous && (
              <DetailRow label="Changes" value={entry.changes_from_previous} />
            )}
            {entry.actions && (
              <DetailRow label="Actions" value={entry.actions} />
            )}
            {entry.camera_movement && (
              <DetailRow label="Camera" value={entry.camera_movement} />
            )}
            {entry.detected_objects.length > 0 && (
              <div className="flex gap-2 items-start">
                <span className="text-xs text-text-3 w-20 shrink-0 pt-0.5">Objects</span>
                <div className="flex flex-wrap gap-1.5">
                  {entry.detected_objects.map((obj, i) => (
                    <span
                      key={i}
                      className="px-2 py-0.5 bg-info/10 text-info rounded-full text-[11px] font-medium border border-info/20"
                    >
                      {obj}
                    </span>
                  ))}
                </div>
              </div>
            )}
        </div>

        {/* Collapsed summary strip — shown when there's extra data but not expanded */}
        {!expanded && hasExtras && (
          <div className="px-4 pb-3 flex flex-wrap gap-x-4 gap-y-0.5">
            {entry.camera_movement && (
              <span className="text-xs text-text-3">
                cam: <span className="text-text-2">{entry.camera_movement}</span>
              </span>
            )}
            {entry.detected_objects.length > 0 && (
              <span className="text-xs text-text-3">
                obj:{' '}
                {entry.detected_objects.map((o, i) => (
                  <span key={i} className="text-info font-medium">{o}{i < entry.detected_objects.length - 1 ? ', ' : ''}</span>
                ))}
              </span>
            )}
            {entry.changes_from_previous && (
              <span className="text-xs text-text-3 italic">↓ tap for changes</span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2 items-start">
      <span className="text-xs text-text-3 w-20 shrink-0 pt-0.5">{label}</span>
      <span className="text-xs text-text-1 leading-relaxed flex-1">{value}</span>
    </div>
  )
}
