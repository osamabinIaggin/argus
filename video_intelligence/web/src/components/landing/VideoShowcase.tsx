import { useState } from 'react'
import { VideoGrid } from '../angus/VideoGrid'
import { VideoTimeline } from '../angus/VideoTimeline'
import { PROJECTS } from '../../data/projects'

export function VideoShowcase() {
  const [hoveredIndex, setHoveredIndex] = useState(-1)
  const [currentIndex, setCurrentIndex] = useState(0)

  const activeIndex = hoveredIndex >= 0 ? hoveredIndex : currentIndex
  const active = PROJECTS[activeIndex]

  return (
    <section className="bg-[#0a0a0b] py-16">
      {/* Section header */}
      <div className="text-center mb-10 px-6">
        <p className="text-xs font-medium uppercase tracking-widest text-white/30 mb-3">
          Proof of intelligence
        </p>
        <h2 className="text-2xl md:text-3xl font-light text-white tracking-tight">
          The AI saw exactly this.
        </h2>
        <p className="text-sm text-white/40 mt-2">
          Hover a video — read what the pipeline understood.
        </p>
      </div>

      {/* Video carousel */}
      <VideoGrid
        setHoveredIndex={setHoveredIndex}
        onScrollIndexChange={setCurrentIndex}
      />

      {/* Timeline seek */}
      <VideoTimeline
        currentIndex={currentIndex}
        onSeek={setCurrentIndex}
      />

      {/* AI summary — fades between videos */}
      <div className="max-w-2xl mx-auto px-6 pb-4 text-center min-h-[120px] flex flex-col items-center justify-center">
        <div key={activeIndex} className="fade-in">
          <p className="text-xs font-medium text-accent uppercase tracking-widest mb-2">
            {active.label}
          </p>
          <p className="text-sm text-white/60 leading-relaxed">
            {active.summary}
          </p>
        </div>
      </div>

      <p className="text-center text-[11px] text-white/20 mt-2 select-none">
        drag to explore
      </p>
    </section>
  )
}
