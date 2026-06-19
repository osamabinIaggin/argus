import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  MessageSquare,
  Bot,
  Search,
  Accessibility,
  Film,
  Shield,
  GraduationCap,
  BarChart3,
  ArrowRight,
} from 'lucide-react'

const USE_CASES = [
  {
    icon: MessageSquare,
    title: 'RAG for Video',
    desc: 'Index timelines & summaries for LLM retrieval',
    detail: 'Use our structured JSON output to build retrieval-augmented generation pipelines. Index keyframe descriptions, timestamps, and detected objects so your LLM can answer questions about video content without re-watching.',
    iconColor: 'text-amber-600',
    iconBg: 'bg-amber-100',
  },
  {
    icon: Bot,
    title: 'Video Agents',
    desc: 'Give AI agents structured video understanding',
    detail: 'Agents get scene descriptions, object lists, and camera movement instead of raw pixels. Power assistants that summarize meetings, find clips by action, or answer "when does X happen?"',
    iconColor: 'text-emerald-600',
    iconBg: 'bg-emerald-100',
  },
  {
    icon: Search,
    title: 'Semantic Search',
    desc: 'Find videos by objects, actions & scenes',
    detail: 'Index your video library by what\'s in each frame. Search for "someone cooking" or "outdoor beach scene" and get timestamped results. Built for content discovery and media management.',
    iconColor: 'text-violet-600',
    iconBg: 'bg-violet-100',
  },
  {
    icon: Accessibility,
    title: 'Accessibility',
    desc: 'Generate captions & audio descriptions',
    detail: 'Turn visual content into text for screen readers and audio descriptions. Create accessible video experiences with scene-aware captions that describe actions, objects, and context.',
    iconColor: 'text-blue-600',
    iconBg: 'bg-blue-100',
  },
  {
    icon: Film,
    title: 'Content Moderation',
    desc: 'Detect objects & flag policy violations',
    detail: 'Identify specific objects, behaviors, or scenes at precise timestamps. Flag policy violations, brand logos, or inappropriate content for human review or automated workflows.',
    iconColor: 'text-rose-600',
    iconBg: 'bg-rose-100',
  },
  {
    icon: Shield,
    title: 'Surveillance',
    desc: 'Monitor feeds for specific behaviors',
    detail: 'Process live or recorded feeds to detect objects, movements, and events. Use structured output for alerts, analytics, or integration with security and monitoring systems.',
    iconColor: 'text-cyan-600',
    iconBg: 'bg-cyan-100',
  },
  {
    icon: GraduationCap,
    title: 'E-Learning',
    desc: 'Searchable lectures & quiz generation',
    detail: 'Make video courses searchable by topic. Generate quizzes from lecture content, track progress by timestamp, and help learners find the exact moment they need to review.',
    iconColor: 'text-indigo-600',
    iconBg: 'bg-indigo-100',
  },
  {
    icon: BarChart3,
    title: 'Ad Detection',
    desc: 'Identify product placements & sponsors',
    detail: 'Detect brand logos, product placements, and sponsored segments. Use for compliance, analytics, or monetization tracking across your video inventory.',
    iconColor: 'text-orange-600',
    iconBg: 'bg-orange-100',
  },
]

function UseCaseCard({ useCase }: { useCase: (typeof USE_CASES)[0] }) {
  const [expanded, setExpanded] = useState(false)
  const { icon: Icon, title, desc, detail, iconColor, iconBg } = useCase

  return (
    <div
      className={[
        'flex-shrink-0 w-80 rounded-xl border overflow-hidden cursor-pointer',
        'bg-surface transition-[border-color,box-shadow] duration-300',
        expanded
          ? 'border-accent/40 shadow-xl ring-1 ring-accent/10'
          : 'border-divider shadow-sm hover:shadow-md hover:border-divider',
      ].join(' ')}
      onMouseEnter={() => setExpanded(true)}
      onMouseLeave={() => setExpanded(false)}
      onClick={() => setExpanded((e) => !e)}
    >
      <div className="p-5">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center mb-3 transition-transform duration-300 ${iconBg} ${iconColor} ${expanded ? 'scale-110' : ''}`}>
          <Icon size={20} />
        </div>
        <h3 className="font-semibold text-text-1 mb-1">{title}</h3>
        <p className="text-sm text-text-2">{desc}</p>

        {/* Always rendered — animated with max-height + opacity for smooth in AND out */}
        <div
          className="overflow-hidden transition-all duration-350 ease-in-out"
          style={{
            maxHeight: expanded ? '200px' : '0px',
            opacity: expanded ? 1 : 0,
            transform: expanded ? 'translateY(0)' : 'translateY(-6px)',
            transition: 'max-height 0.35s ease, opacity 0.25s ease, transform 0.25s ease',
          }}
        >
          <div className="mt-4 pt-4 border-t border-divider">
            <p className="text-sm text-text-2 leading-relaxed mb-4">{detail}</p>
            <Link
              to="/try"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-accent hover:text-accent-dark transition-colors"
            >
              Try it out
              <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}

export function ScrollingUseCases() {
  const row1 = [...USE_CASES, ...USE_CASES]
  const row2 = [...[...USE_CASES].reverse(), ...[...USE_CASES].reverse()]

  return (
    <section id="use-cases" className="py-16 overflow-hidden scroll-mt-20">
      <div className="text-center mb-10">
        <h2 className="text-sm font-medium uppercase tracking-widest text-text-3 mb-2">
          Use cases
        </h2>
        <p className="text-2xl md:text-3xl font-bold text-text-1 max-w-2xl mx-auto">
          Built for AI. Powering the next generation of video apps.
        </p>
      </div>

      <div className="flex gap-4 mb-4 overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_10%,black_90%,transparent)]">
        <div className="flex gap-4 animate-marquee">
          {row1.map((uc, i) => (
            <UseCaseCard key={`r1-${i}`} useCase={uc} />
          ))}
        </div>
      </div>

      <div className="flex gap-4 overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_10%,black_90%,transparent)]">
        <div className="flex gap-4 animate-marquee-reverse">
          {row2.map((uc, i) => (
            <UseCaseCard key={`r2-${i}`} useCase={uc} />
          ))}
        </div>
      </div>
    </section>
  )
}
