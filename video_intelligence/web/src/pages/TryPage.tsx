import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Video, BookOpen, Code } from 'lucide-react'
import { PlaygroundContent } from '../components/playground/PlaygroundContent'
import { GetKeyModal } from '../components/landing/GetKeyModal'
import { Button } from '../components/ui/Button'

export default function TryPage() {
  const [showKeyModal, setShowKeyModal] = useState(false)

  return (
    <div className="min-h-screen bg-page">
      {/* Try layout navbar */}
      <nav className="sticky top-0 z-40 bg-page/80 backdrop-blur-sm border-b border-divider">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 font-semibold text-text-1">
            <Video size={20} className="text-accent" />
            <span>Video Intelligence</span>
          </Link>

          <div className="flex items-center gap-4 text-sm">
            <Link
              to="/try"
              className="text-accent font-medium"
            >
              Try it
            </Link>
            <Link
              to="/docs"
              className="text-text-2 hover:text-text-1 transition-colors flex items-center gap-1.5"
            >
              <BookOpen size={14} />
              Docs
            </Link>
            <Link
              to="/developers"
              className="text-text-2 hover:text-text-1 transition-colors flex items-center gap-1.5"
            >
              <Code size={14} />
              For developers
            </Link>
            <Button size="sm" onClick={() => setShowKeyModal(true)}>
              Get API Key
            </Button>
          </div>
        </div>
      </nav>

      <div className="max-w-5xl mx-auto px-6 py-8">
        <PlaygroundContent
          title="Try Video Intelligence"
          requireKeyPrompt
          onKeyRequired={() => setShowKeyModal(true)}
        />
      </div>

      <GetKeyModal
        open={showKeyModal}
        onClose={() => setShowKeyModal(false)}
        onSuccess={(_key) => {
          // Stay on /try — key is saved by GetKeyModal via setApiKey
          setShowKeyModal(false)
        }}
      />
    </div>
  )
}
