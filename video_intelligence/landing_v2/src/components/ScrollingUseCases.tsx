import {
  MessageSquare,
  Bot,
  Search,
  Accessibility,
  Film,
  Shield,
  GraduationCap,
  BarChart3,
} from 'lucide-react'

const USE_CASES = [
  { icon: MessageSquare, title: 'RAG for Video', desc: 'Index timelines & summaries for LLM retrieval', iconColor: 'text-amber-400' },
  { icon: Bot, title: 'Video Agents', desc: 'Give AI agents structured video understanding', iconColor: 'text-emerald-400' },
  { icon: Search, title: 'Semantic Search', desc: 'Find videos by objects, actions & scenes', iconColor: 'text-violet-400' },
  { icon: Accessibility, title: 'Accessibility', desc: 'Generate captions & audio descriptions', iconColor: 'text-blue-400' },
  { icon: Film, title: 'Content Moderation', desc: 'Detect objects & flag policy violations', iconColor: 'text-rose-400' },
  { icon: Shield, title: 'Surveillance', desc: 'Monitor feeds for specific behaviors', iconColor: 'text-cyan-400' },
  { icon: GraduationCap, title: 'E-Learning', desc: 'Searchable lectures & quiz generation', iconColor: 'text-indigo-400' },
  { icon: BarChart3, title: 'Ad Detection', desc: 'Identify product placements & sponsors', iconColor: 'text-orange-400' },
]

function UseCaseCard({
  icon: Icon,
  title,
  desc,
  iconColor,
}: (typeof USE_CASES)[0]) {
  return (
    <div className="flex-shrink-0 w-72 rounded-2xl border border-divider p-5 bg-surface hover:border-text-3 transition-colors">
      <div className={`w-10 h-10 rounded-xl bg-surface-2 flex items-center justify-center mb-3 ${iconColor}`}>
        <Icon size={20} />
      </div>
      <h3 className="font-semibold text-text-1 mb-1">{title}</h3>
      <p className="text-sm text-text-3">{desc}</p>
    </div>
  )
}

export function ScrollingUseCases() {
  const row1 = [...USE_CASES, ...USE_CASES]
  const row2 = [...[...USE_CASES].reverse(), ...[...USE_CASES].reverse()]

  return (
    <section id="use-cases" className="py-12 overflow-hidden scroll-mt-20">
      <div className="text-center mb-8">
        <h2 className="text-sm font-medium uppercase tracking-widest text-text-3 mb-2">
          Use cases
        </h2>
        <p className="text-2xl md:text-3xl font-bold text-text-1 max-w-2xl mx-auto">
          Built for AI. Powering the next generation of video apps.
        </p>
      </div>

      {/* Row 1 — scroll left */}
      <div className="flex gap-4 mb-4 overflow-hidden">
        <div className="flex gap-4 animate-marquee">
          {row1.map((uc, i) => (
            <UseCaseCard key={`r1-${i}`} {...uc} />
          ))}
        </div>
      </div>

      {/* Row 2 — scroll right */}
      <div className="flex gap-4 overflow-hidden">
        <div className="flex gap-4 animate-marquee-reverse">
          {row2.map((uc, i) => (
            <UseCaseCard key={`r2-${i}`} {...uc} />
          ))}
        </div>
      </div>
    </section>
  )
}
