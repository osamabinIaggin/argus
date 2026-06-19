import { useState, useRef, useEffect, useCallback } from 'react'
import { PROJECTS } from '../../data/projects'

const CARD_W = 420
const CARD_H = Math.round(CARD_W * 9 / 16)   // 16:9 = 236px
const GAP = 28
const SLOT = CARD_W + GAP
const STAGGER = 44   // px — even cards shift up, odd cards shift down
const SINGLE_WIDTH = PROJECTS.length * SLOT
const SCROLL_SPEED = 0.55   // px per frame
const DRAG_SENSITIVITY = 3  // multiplier — raise for more sensitivity

interface VideoCardProps {
  project: (typeof PROJECTS)[0]
  onHover: () => void
  onLeave: () => void
}

function VideoCard({ project, onHover, onLeave }: VideoCardProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [hovered, setHovered] = useState(false)

  const handleEnter = () => {
    setHovered(true)
    videoRef.current?.play().catch(() => {})
    onHover()
  }
  const handleLeave = () => {
    setHovered(false)
    videoRef.current?.pause()
    onLeave()
  }

  return (
    <div
      className="flex-shrink-0 flex flex-row rounded-xl overflow-hidden transition-[border-color,box-shadow] duration-300"
      style={{
        height: CARD_H,
        border: `1px solid ${hovered ? 'rgba(218,119,86,0.45)' : 'rgba(255,255,255,0.08)'}`,
        boxShadow: hovered ? '0 6px 28px -6px rgba(218,119,86,0.28)' : 'none',
      }}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      {/* Video panel */}
      <div className="flex-shrink-0 bg-black" style={{ width: CARD_W }}>
        <video
          ref={videoRef}
          src={project.videoSrc}
          muted
          loop
          playsInline
          preload="metadata"
          className="w-full h-full object-cover"
        />
      </div>

      {/* Description — slides in horizontally on hover */}
      <div
        className="overflow-hidden flex-shrink-0 bg-[#111113]"
        style={{
          maxWidth: hovered ? 300 : 0,
          opacity: hovered ? 1 : 0,
          transition: 'max-width 0.35s ease, opacity 0.2s ease',
        }}
      >
        <div
          className="flex flex-col justify-center p-6"
          style={{ width: 300, height: CARD_H }}
        >
          <p className="text-[10px] font-medium text-accent uppercase tracking-widest mb-1.5">
            {project.label}
          </p>
          <h3 className="text-sm font-semibold text-white mb-2 leading-snug">
            {project.title}
          </h3>
          <p className="text-xs text-white/55 leading-relaxed line-clamp-4">
            {project.summary}
          </p>
        </div>
      </div>
    </div>
  )
}

interface VideoGridProps {
  setHoveredIndex: (i: number) => void
  onScrollIndexChange?: (index: number) => void
}

export function VideoGrid({ setHoveredIndex, onScrollIndexChange }: VideoGridProps) {
  const innerRef = useRef<HTMLDivElement>(null)
  const offsetRef = useRef(0)
  const rafRef = useRef(0)
  const dragRef = useRef({ active: false, lastX: 0 })
  const pausedRef = useRef(false)
  const lastIdxRef = useRef(-1)
  const tickRef = useRef<() => void>(() => {})

  const cards = [...PROJECTS, ...PROJECTS]

  useEffect(() => {
    function tick() {
      if (!pausedRef.current && !dragRef.current.active) {
        offsetRef.current += SCROLL_SPEED
        if (offsetRef.current >= SINGLE_WIDTH) offsetRef.current -= SINGLE_WIDTH
      }
      if (innerRef.current) {
        innerRef.current.style.transform = `translateX(-${offsetRef.current}px)`
      }
      const idx =
        Math.floor((offsetRef.current / SINGLE_WIDTH) * PROJECTS.length) % PROJECTS.length
      if (idx !== lastIdxRef.current) {
        lastIdxRef.current = idx
        onScrollIndexChange?.(idx)
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    tickRef.current = tick
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [onScrollIndexChange])

  const handlePointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    e.preventDefault()
    dragRef.current = { active: true, lastX: e.clientX }
    ;(e.currentTarget as HTMLDivElement).setPointerCapture(e.pointerId)
  }, [])

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragRef.current.active) return
    const dx = dragRef.current.lastX - e.clientX
    dragRef.current.lastX = e.clientX
    offsetRef.current += dx * DRAG_SENSITIVITY
    if (offsetRef.current < 0) offsetRef.current += SINGLE_WIDTH
    if (offsetRef.current >= SINGLE_WIDTH) offsetRef.current -= SINGLE_WIDTH
  }, [])

  const handlePointerUp = useCallback(() => {
    dragRef.current.active = false
  }, [])

  return (
    <div
      className="select-none cursor-grab active:cursor-grabbing"
      style={{
        overflowX: 'clip',
        overflowY: 'visible',
        touchAction: 'pan-y',
        WebkitMaskImage:
          'linear-gradient(to right, transparent, black 8%, black 92%, transparent)',
        maskImage:
          'linear-gradient(to right, transparent, black 8%, black 92%, transparent)',
      }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerLeave={handlePointerUp}
    >
      <div
        ref={innerRef}
        className="flex items-center"
        style={{ gap: GAP, width: cards.length * SLOT, paddingTop: STAGGER + 16, paddingBottom: STAGGER + 16 }}
      >
        {cards.map((p, i) => (
          <div
            key={`${p.id}-${i}`}
            className="flex-shrink-0"
            style={{ transform: `translateY(${i % 2 === 0 ? -STAGGER : STAGGER}px)` }}
          >
            <VideoCard
              project={p}
              onHover={() => {
                setHoveredIndex(i % PROJECTS.length)
                pausedRef.current = true
              }}
              onLeave={() => {
                setHoveredIndex(-1)
                pausedRef.current = false
              }}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
