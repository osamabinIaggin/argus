import { Play, BookOpen, ChevronDown, MessageSquare, Bot, Search } from 'lucide-react'
import { urls } from '../config'

const HERO_USE_CASES = [
  { icon: MessageSquare, label: 'RAG & Chat' },
  { icon: Bot, label: 'AI Agents' },
  { icon: Search, label: 'Semantic Search' },
]

export function Hero() {
  return (
    <section className="relative min-h-[52vh] flex flex-col items-center justify-center px-6 pt-20 pb-6 text-center">
      {/* New feature highlight */}
      <a
        href={urls.developers}
        className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-success/20 text-success text-sm font-medium mb-8 hover:bg-success/30 transition-colors"
      >
        <span className="w-1.5 h-1.5 bg-success rounded-full animate-pulse" />
        Introducing AI Video Analysis →
      </a>

      <h1 className="text-4xl sm:text-5xl md:text-6xl font-bold text-text-1 leading-tight tracking-tight max-w-4xl mx-auto mb-6">
        All your video.{' '}
        <span className="gradient-text">One intelligence layer.</span>
      </h1>

      <p className="text-lg text-text-2 max-w-2xl mx-auto mb-10">
        Video Intelligence is an AI-powered platform that turns any video into structured data — timelines, summaries, object detection, and chat. Built for LLMs and agents.
      </p>

      <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
        <a
          href={urls.try}
          className="inline-flex items-center gap-2 px-6 py-3.5 rounded-xl font-semibold text-bg bg-gradient-to-r from-white via-accent-glow/90 to-white/90 glow-subtle hover:opacity-95 transition-opacity"
        >
          <Play size={18} />
          Get started (for free)
        </a>
        <a
          href={urls.docs}
          className="inline-flex items-center gap-2 px-6 py-3.5 rounded-xl font-medium text-text-1 bg-surface border border-divider hover:border-text-3 hover:bg-surface-2 transition-colors"
        >
          <BookOpen size={18} />
          Read the docs
        </a>
      </div>

      <p className="text-sm text-text-3 mt-6">
        Free tier: 60 minutes/month · No credit card required
      </p>

      {/* Compact use case preview — visible above the fold */}
      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        {HERO_USE_CASES.map(({ icon: Icon, label }) => (
          <div
            key={label}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-surface/80 border border-divider text-text-2 text-sm"
          >
            <Icon size={16} className="text-accent" />
            <span>{label}</span>
          </div>
        ))}
      </div>

      {/* Scroll indicator — clear spacing from content above */}
      <a
        href="#use-cases"
        className="mt-10 mb-4 flex flex-col items-center gap-1 text-text-3 hover:text-accent transition-colors group"
      >
        <span className="text-xs font-medium uppercase tracking-widest">See all use cases</span>
        <ChevronDown size={20} className="animate-bounce group-hover:text-accent" />
      </a>
    </section>
  )
}
