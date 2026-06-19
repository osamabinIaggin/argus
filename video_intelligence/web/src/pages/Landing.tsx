import { lazy, Suspense } from 'react'
import { Link } from 'react-router-dom'
import { Video } from 'lucide-react'
import { Navbar } from '../components/layout/Navbar'
import { HeroSection } from '../components/landing/HeroSection'
import { ScrollingUseCases } from '../components/landing/ScrollingUseCases'
import { HowItWorks } from '../components/landing/HowItWorks'
import { FeaturesSection } from '../components/landing/FeaturesSection'
import { PricingSection } from '../components/landing/PricingSection'

// Three.js is heavy — lazy-load the video showcase so the hero loads instantly
const VideoShowcase = lazy(() =>
  import('../components/landing/VideoShowcase').then((m) => ({ default: m.VideoShowcase }))
)

export default function Landing() {
  return (
    <div className="min-h-screen w-full overflow-x-hidden bg-page flex flex-col">
      <Navbar />
      <main className="flex-1">
        {/* 1. Hero — what it is + JSON preview */}
        <HeroSection />

        {/* 2. Video showcase — proof the AI actually understands video */}
        <Suspense fallback={
          <div className="h-[70vh] bg-[#0a0a0b] flex items-center justify-center">
            <div className="flex flex-col items-center gap-4">
              <div className="w-12 h-12 rounded-full border-2 border-accent/30 border-t-accent animate-spin" />
              <p className="text-sm text-text-3 animate-pulse">Loading 3D showcase…</p>
            </div>
          </div>
        }>
          <VideoShowcase />
        </Suspense>

        {/* 3. Use cases — breadth of what you can build */}
        <ScrollingUseCases />

        {/* 3. How it works — simple 3-step process */}
        <HowItWorks />

        {/* 4. Features — technical depth for developers */}
        <FeaturesSection />

        {/* 5. Pricing — convert */}
        <PricingSection />
      </main>

      <footer className="border-t border-divider py-8">
        <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-text-2 text-sm">
            <Video size={16} className="text-accent" />
            <span className="font-medium">Video Intelligence</span>
          </div>
          <div className="flex items-center gap-5 text-sm text-text-2">
            <Link to="/try" className="hover:text-text-1 transition-colors">Try it</Link>
            <Link to="/docs" className="hover:text-text-1 transition-colors">Docs</Link>
            <Link to="/developers" className="hover:text-text-1 transition-colors">For developers</Link>
          </div>
          <div className="text-sm text-text-3">© 2026 Video Intelligence</div>
        </div>
      </footer>
    </div>
  )
}
