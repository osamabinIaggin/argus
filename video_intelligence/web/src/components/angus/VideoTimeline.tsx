import { useRef, useEffect } from 'react'
import gsap from 'gsap'
import { PROJECTS } from '../../data/projects'

interface VideoTimelineProps {
  currentIndex: number
  onSeek?: (index: number) => void
}

export function VideoTimeline({ currentIndex, onSeek }: VideoTimelineProps) {
  const trackRef = useRef<HTMLDivElement>(null)
  const indicatorRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!indicatorRef.current) return
    const pct = PROJECTS.length > 1 ? (currentIndex / (PROJECTS.length - 1)) * 100 : 0
    gsap.to(indicatorRef.current, { left: `${pct}%`, duration: 0.5, ease: 'power2.out', overwrite: true })
  }, [currentIndex])

  return (
    <div className="w-full max-w-2xl mx-auto px-6 py-6">
      <div
        ref={trackRef}
        className="relative h-px cursor-pointer border-t border-dashed border-white/30"
        onClick={(e) => {
          if (!trackRef.current || !onSeek) return
          const rect = trackRef.current.getBoundingClientRect()
          const pct = (e.clientX - rect.left) / rect.width
          onSeek(Math.min(PROJECTS.length - 1, Math.max(0, Math.round(pct * (PROJECTS.length - 1)))))
        }}
      >
        <div
          ref={indicatorRef}
          className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-white"
          style={{ left: '0%' }}
        />
      </div>
      <div className="flex justify-between mt-3">
        {PROJECTS.map((p, i) => (
          <button
            key={p.id}
            onClick={() => onSeek?.(i)}
            className={`text-xs tabular-nums transition-colors duration-300 ${currentIndex === i ? 'text-white font-medium' : 'text-white/40 hover:text-white/70'}`}
          >
            {String(i + 1).padStart(2, '0')}
          </button>
        ))}
      </div>
    </div>
  )
}
