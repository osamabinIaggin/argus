/** Placeholder logos — use real logos or remove in production */
const LOGOS = [
  'AI Teams',
  'Developers',
  'Enterprises',
  'Startups',
  'Researchers',
  'Content Creators',
]

export function TrustedBy() {
  return (
    <section className="py-8 border-y border-divider">
      <p className="text-center text-xs font-medium uppercase tracking-widest text-text-3 mb-8">
        Trusted by teams building with AI
      </p>
      <div className="flex flex-wrap items-center justify-center gap-x-12 gap-y-6">
        {LOGOS.map((name) => (
          <div
            key={name}
            className="text-text-3 text-sm font-medium hover:text-text-2 transition-colors"
          >
            {name}
          </div>
        ))}
      </div>
    </section>
  )
}
