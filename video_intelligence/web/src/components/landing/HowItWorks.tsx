import { Upload, Cpu, FileJson } from 'lucide-react'

const steps = [
  {
    icon: Upload,
    number: '01',
    title: 'Upload or link a video',
    description: 'POST a file or HTTPS URL. We support MP4, MOV, AVI, MKV, and WebM up to 500 MB.',
  },
  {
    icon: Cpu,
    number: '02',
    title: 'Pipeline runs automatically',
    description: 'Scene detection, pHash deduplication, YOLO object recognition, audio analysis, and Gemini vision AI — all in sequence.',
  },
  {
    icon: FileJson,
    number: '03',
    title: 'Receive structured JSON',
    description: 'A timestamped timeline of keyframes with descriptions, camera movements, objects, and a full video summary.',
  },
]

export function HowItWorks() {
  return (
    <section className="max-w-6xl mx-auto px-6 py-16">
      <div className="text-center mb-12">
        <h2 className="text-3xl font-bold text-text-1 mb-3">How it works</h2>
        <p className="text-text-2">Three steps from video to intelligence.</p>
      </div>

      <div className="grid md:grid-cols-3 gap-8 relative">
        {/* Connector line */}
        <div className="hidden md:block absolute top-10 left-[calc(16.67%+1rem)] right-[calc(16.67%+1rem)] h-px bg-divider" />

        {steps.map(({ icon: Icon, number, title, description }) => (
          <div key={number} className="flex flex-col items-center text-center relative">
            <div className="w-20 h-20 rounded-full bg-accent/10 flex items-center justify-center mb-4 ring-4 ring-page relative z-10">
              <Icon size={28} className="text-accent" />
            </div>
            <div className="text-xs font-bold text-text-3 mb-1 tracking-widest">{number}</div>
            <h3 className="text-base font-semibold text-text-1 mb-2">{title}</h3>
            <p className="text-sm text-text-2 leading-relaxed">{description}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
