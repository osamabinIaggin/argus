import { useRef, useEffect } from 'react'
import gsap from 'gsap'
import { PROJECTS } from '../../data/projects'

interface TimelineProps {
  currentIndex: number
  onSeek?: (index: number) => void
}

export function Timeline({ currentIndex, onSeek }: TimelineProps) {
  const trackRef = useRef<HTMLDivElement>(null)
  const indicatorRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!indicatorRef.current) return
    const pct = PROJECTS.length > 1 ? (currentIndex / (PROJECTS.length - 1)) * 100 : 0
    gsap.to(indicatorRef.current, {
      left: `${pct}%`,
      duration: 0.5,
      ease: 'power2.out',
      overwrite: true,
    })
  }, [currentIndex])

  return (
    <div className="w-full max-w-2xl mx-auto px-6 py-8">
      <div
        ref={trackRef}
        className="relative h-px cursor-pointer border-t border-dashed border-white/30"
        onClick={(e) => {
          if (!trackRef.current || !onSeek) return
          const rect = trackRef.current.getBoundingClientRect()
          const x = e.clientX - rect.left
          const pct = x / rect.width
          const idx = Math.min(
            PROJECTS.length - 1,
            Math.max(0, Math.round(pct * (PROJECTS.length - 1)))
          )
          onSeek(idx)
        }}
      >
        <div
          ref={indicatorRef}
          className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white"
          style={{ left: '0%' }}
        />
      </div>
      <div className="flex justify-between mt-4 text-sm">
        {PROJECTS.map((p, i) => (
          <span
            key={p.id}
            className={`tabular-nums transition-colors ${currentIndex === i ? 'text-white font-medium' : 'text-white/50'}`}
          >
            {p.title}
          </span>
        ))}
      </div>
    </div>
  )
}
