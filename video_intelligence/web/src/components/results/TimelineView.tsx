import { KeyframeCard } from './KeyframeCard'
import type { KeyframeEntry } from '../../types'

interface TimelineViewProps {
  timeline: KeyframeEntry[]
}

export function TimelineView({ timeline }: TimelineViewProps) {
  if (timeline.length === 0) {
    return (
      <div className="text-center py-12 text-text-3 text-sm">No keyframes found.</div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {timeline.map((entry) => (
        <KeyframeCard
          key={entry.keyframe_id}
          entry={entry}
          isSceneStart={entry.scene_change}
        />
      ))}
    </div>
  )
}
