import { useState } from 'react'
import { LoadingScreen } from '../components/angus/LoadingScreen'
import { VideoGrid } from '../components/angus/VideoGrid'
import { Timeline } from '../components/angus/Timeline'
import { useLenis } from '../hooks/useLenis'

export default function AngusPage() {
  const [loaded, setLoaded] = useState(false)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [hoveredIndex, setHoveredIndex] = useState(-1)
  const [scrollToIndex, setScrollToIndex] = useState<number | null>(null)

  useLenis()

  // Timeline shows hovered video, or last clicked
  const timelineIndex = hoveredIndex >= 0 ? hoveredIndex : currentIndex

  const handleScrollToIndexHandled = () => setScrollToIndex(null)

  return (
    <div className="min-h-screen bg-[#1E1E1E] text-white">
      {!loaded && <LoadingScreen onComplete={() => setLoaded(true)} />}

      <main className={`transition-opacity duration-500 ${loaded ? 'opacity-100' : 'opacity-0'}`}>
        {/* Header */}
        <header className="fixed top-0 left-0 right-0 z-40 px-6 py-6 flex justify-between items-center">
          <span className="font-light text-lg tracking-tight">Video Intelligence</span>
          <a
            href="/try"
            className="text-sm text-white/70 hover:text-white transition-colors"
          >
            Try it →
          </a>
        </header>

        {/* Hero / Video grid */}
        <section className="min-h-screen flex flex-col items-center justify-center pt-20">
          <div className="text-center mb-8">
            <h1 className="text-4xl md:text-6xl font-light tracking-tight mb-4">
              Turn any video into structured AI.
            </h1>
            <p className="text-white/60 max-w-xl mx-auto">
              Hover over a project to play. Built for LLMs & agents.
            </p>
          </div>

          <VideoGrid
            hoveredIndex={hoveredIndex}
            setHoveredIndex={setHoveredIndex}
            scrollToIndex={scrollToIndex}
            onScrollToIndexHandled={handleScrollToIndexHandled}
            onScrollIndexChange={setCurrentIndex}
          />
        </section>

        {/* Timeline */}
        <section className="py-12 border-t border-white/10">
          <Timeline currentIndex={timelineIndex} onSeek={(i) => { setCurrentIndex(i); setScrollToIndex(i) }} />
        </section>

        {/* Footer */}
        <footer className="py-12 text-center text-white/40 text-sm">
          © 2025 Video Intelligence
        </footer>
      </main>
    </div>
  )
}
