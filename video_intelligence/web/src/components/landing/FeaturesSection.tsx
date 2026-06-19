import { ScanSearch, Box, Eye } from 'lucide-react'

const features = [
  {
    icon: ScanSearch,
    title: 'Smart keyframe extraction',
    description:
      'PySceneDetect streams scene boundaries in real-time. pHash deduplication removes near-identical frames while guaranteeing at least one keyframe per scene.',
    tags: ['PySceneDetect', 'pHash', 'OpenCV'],
  },
  {
    icon: Box,
    title: 'Object detection',
    description:
      'YOLOv8n runs on every keyframe, annotating each with detected objects and confidence scores — enriching the vision model context.',
    tags: ['YOLOv8n', 'Per-frame', 'Confidence scores'],
  },
  {
    icon: Eye,
    title: 'Vision AI descriptions',
    description:
      'Gemini 2.5 Flash describes each keyframe with audio context injected per segment, producing rich, grounded natural language output.',
    tags: ['Gemini Flash', 'Audio context', 'Per-frame'],
  },
]

export function FeaturesSection() {
  return (
    <section id="features" className="bg-surface-2 py-20">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold text-text-1 mb-3">Built for precision</h2>
          <p className="text-text-2 max-w-xl mx-auto">
            Every component of the pipeline is tuned for accuracy, cost-efficiency, and developer experience.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {features.map(({ icon: Icon, title, description, tags }) => (
            <div key={title} className="bg-surface rounded-xl border border-divider p-6 shadow-sm">
              <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center mb-4">
                <Icon size={20} className="text-accent" />
              </div>
              <h3 className="font-semibold text-text-1 mb-2">{title}</h3>
              <p className="text-sm text-text-2 leading-relaxed mb-4">{description}</p>
              <div className="flex flex-wrap gap-1.5">
                {tags.map((tag) => (
                  <span
                    key={tag}
                    className="px-2 py-0.5 bg-surface-2 text-text-3 text-xs rounded-full border border-divider"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
