import { useState, useRef, useCallback, useEffect } from 'react'
import { Suspense } from 'react'
import { Canvas } from '@react-three/fiber'
import { VideoPlane } from './VideoPlane'
import { PROJECTS } from '../../data/projects'

const DEFORM_STRENGTH = 0.03

function SceneContent({
  hoveredIndex,
  setHoveredIndex,
  scrollOffset,
}: {
  hoveredIndex: number
  setHoveredIndex: (i: number) => void
  scrollOffset: number
}) {
  const loopedProjects = Array.from({ length: LOOP_COUNT }, () => [...PROJECTS]).flat()
  return (
    <group position={[-scrollOffset, 0, 0]}>
      <ambientLight intensity={0.5} />
      <pointLight position={[10, 10, 10]} intensity={1} />
      {loopedProjects.map((p, i) => (
        <VideoPlane
          key={`${p.id}-${i}`}
          videoSrc={p.videoSrc}
          index={i}
          total={loopedProjects.length}
          isHovered={hoveredIndex === i % SLOTS}
          deformStrength={DEFORM_STRENGTH}
          onHover={() => setHoveredIndex(i % SLOTS)}
          onLeave={() => setHoveredIndex(-1)}
        />
      ))}
    </group>
  )
}

interface VideoGridProps {
  hoveredIndex: number
  setHoveredIndex: (i: number) => void
  scrollToIndex?: number | null
  onScrollToIndexHandled?: () => void
  onScrollIndexChange?: (index: number) => void
}

const SLOTS = PROJECTS.length
const LOOP_COUNT = 4
const TOTAL_SLOTS = SLOTS * LOOP_COUNT
/** vw per slot — smaller = more videos visible at once */
const VW_PER_SLOT = 28
/** Drag sensitivity — higher = more scroll per pixel of mouse movement */
const DRAG_SENSITIVITY = 1.8

export function VideoGrid({ hoveredIndex, setHoveredIndex, scrollToIndex, onScrollToIndexHandled, onScrollIndexChange }: VideoGridProps) {
  const [scrollOffset, setScrollOffset] = useState(0)
  const scrollRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef({ active: false, startX: 0, startScrollLeft: 0 })

  const loopWidthPx = () => {
    const el = scrollRef.current
    if (!el) return 0
    return el.scrollWidth / LOOP_COUNT
  }
  const wrapThreshold = () => loopWidthPx() * (LOOP_COUNT - 1)

  useEffect(() => {
    if (scrollToIndex == null || scrollToIndex < 0) return
    const el = scrollRef.current
    if (!el) return
    const thresh = wrapThreshold()
    if (thresh <= 0) return
    const progress = scrollToIndex / (SLOTS - 1)
    el.scrollTo({ left: progress * thresh, behavior: 'smooth' })
    onScrollToIndexHandled?.()
  }, [scrollToIndex, onScrollToIndexHandled])

  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const thresh = wrapThreshold()
    if (thresh <= 0) return
    let sl = el.scrollLeft
    if (sl >= thresh) {
      el.scrollLeft = sl - thresh
      return
    }
    const progress = Math.min(1, Math.max(0, sl / thresh))
    const slotWidth3D = 3.2
    setScrollOffset(progress * SLOTS * slotWidth3D)
    const index = Math.round(progress * (SLOTS - 1)) % SLOTS
    onScrollIndexChange?.(index)
  }, [onScrollIndexChange])

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      const el = scrollRef.current
      if (!el) return
      el.scrollLeft += e.deltaY
      e.preventDefault()
      e.stopPropagation()
    },
    []
  )

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return
    e.preventDefault()
    dragRef.current = { active: true, startX: e.clientX, startScrollLeft: scrollRef.current?.scrollLeft ?? 0 }
  }, [])

  const doDrag = useCallback((clientX: number) => {
    const el = scrollRef.current
    if (!el || !dragRef.current.active) return
    const thresh = el.scrollWidth / LOOP_COUNT * (LOOP_COUNT - 1)
    const dx = (dragRef.current.startX - clientX) * DRAG_SENSITIVITY
    let newScroll = dragRef.current.startScrollLeft + dx
    if (newScroll >= thresh) {
      newScroll -= thresh
      dragRef.current.startScrollLeft = newScroll
      dragRef.current.startX = clientX
    } else if (newScroll < 0) {
      newScroll += thresh
      dragRef.current.startScrollLeft = newScroll
      dragRef.current.startX = clientX
    }
    el.scrollLeft = Math.max(0, Math.min(thresh, newScroll))
  }, [])

  const handleMouseMove = useCallback((e: React.MouseEvent) => doDrag(e.clientX), [doDrag])

  const handleMouseUp = useCallback(() => {
    dragRef.current.active = false
  }, [])

  const handleMouseLeave = useCallback(() => {
    dragRef.current.active = false
  }, [])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragRef.current.active) return
      const el = scrollRef.current
      if (!el) return
      const thresh = el.scrollWidth / LOOP_COUNT * (LOOP_COUNT - 1)
      const dx = (dragRef.current.startX - e.clientX) * DRAG_SENSITIVITY
      let newScroll = dragRef.current.startScrollLeft + dx
      if (newScroll >= thresh) {
        newScroll -= thresh
        dragRef.current.startScrollLeft = newScroll
        dragRef.current.startX = e.clientX
      } else if (newScroll < 0) {
        newScroll += thresh
        dragRef.current.startScrollLeft = newScroll
        dragRef.current.startX = e.clientX
      }
      el.scrollLeft = Math.max(0, Math.min(thresh, newScroll))
    }
    const onUp = () => { dragRef.current.active = false }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  return (
    <div className="relative w-full h-[70vh] min-h-[500px] select-none" data-lenis-prevent>
      {/* Horizontal scroll container (behind) */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="absolute inset-0 overflow-x-auto overflow-y-hidden scrollbar-hide"
      >
        <div
          className="h-full"
          style={{ width: `${TOTAL_SLOTS * VW_PER_SLOT}vw`, minWidth: `${TOTAL_SLOTS * VW_PER_SLOT}vw` }}
        />
      </div>

      {/* Canvas overlay — wheel + drag for scroll */}
      <div
        className="absolute inset-0 cursor-grab active:cursor-grabbing"
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        style={{ pointerEvents: 'auto' }}
      >
        <Canvas
          camera={{ position: [0, 0, 6], fov: 50 }}
          gl={{ alpha: true, antialias: true }}
          className="w-full h-full"
        >
          <Suspense fallback={null}>
            <SceneContent
              hoveredIndex={hoveredIndex}
              setHoveredIndex={setHoveredIndex}
              scrollOffset={scrollOffset}
            />
          </Suspense>
        </Canvas>
      </div>

      {/* Overlay labels */}
      <div className="absolute bottom-0 left-0 right-0 p-6 flex flex-wrap gap-4 justify-center pointer-events-none">
        {PROJECTS.map((p, i) => (
          <div
            key={p.id}
            className={`text-sm transition-opacity duration-300 ${hoveredIndex === i ? 'opacity-100' : 'opacity-50'}`}
          >
            <span className="font-medium text-white">{p.title}</span>
            <span className="text-white/60 ml-2">{p.date}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
