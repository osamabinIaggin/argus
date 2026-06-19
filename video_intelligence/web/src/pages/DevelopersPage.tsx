import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Video,
  Key,
  BookOpen,
  List,
  LayoutDashboard,
} from 'lucide-react'
import { GetKeyModal } from '../components/landing/GetKeyModal'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { CopyButton } from '../components/ui/CopyButton'

const QUICKSTART_PYTHON = `import requests, time

API_KEY = "vi_live_..."
BASE = "https://your-server.com/v1"  # your Video Intelligence server
headers = {"Authorization": f"Bearer {API_KEY}"}

# 1. Upload video
r = requests.post(f"{BASE}/analyze", headers=headers,
    files={"file": open("video.mp4", "rb")}, data={"fps": 5})
vid = r.json()["video_id"]

# 2. Poll until complete
while requests.get(f"{BASE}/status/{vid}", headers=headers).json()["status"] != "complete":
    time.sleep(2)

# 3. Get result
result = requests.get(f"{BASE}/result/{vid}", headers=headers).json()
print(result["summary"])`

const QUICKSTART_CURL = `# Create key (no auth)
curl -X POST https://your-server.com/v1/keys \\
  -H "Content-Type: application/json" \\
  -d '{"name": "My App", "plan": "free"}'

# Analyze video
curl -X POST https://your-server.com/v1/analyze \\
  -H "Authorization: Bearer $API_KEY" \\
  -F "file=@video.mp4" \\
  -F "fps=5"`

export default function DevelopersPage() {
  const [showKeyModal, setShowKeyModal] = useState(false)

  return (
    <div className="min-h-screen bg-page">
      {/* Nav */}
      <nav className="sticky top-0 z-40 bg-page/80 backdrop-blur-sm border-b border-divider">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 font-semibold text-text-1">
            <Video size={18} className="text-accent" />
            Video Intelligence
          </Link>
          <div className="flex items-center gap-4 text-sm">
            <Link to="/try" className="text-text-2 hover:text-text-1 transition-colors">
              Try it
            </Link>
            <Link to="/docs" className="text-text-2 hover:text-text-1 transition-colors">
              Docs
            </Link>
            <Button size="sm" onClick={() => setShowKeyModal(true)}>
              Get API Key
            </Button>
          </div>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-6 py-12">
        <h1 className="text-3xl font-bold text-text-1 mb-2">For developers</h1>
        <p className="text-text-2 mb-10">
          Build with our API. Get an API key, read the docs, and start integrating.
        </p>

        {/* Quick links */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-12">
          <Link to="/docs" className="no-underline">
            <Card className="flex items-center gap-3 p-4 hover:border-accent/40 hover:shadow transition-all cursor-pointer">
              <div className="w-10 h-10 rounded-lg bg-info/10 flex items-center justify-center">
                <BookOpen size={20} className="text-info" />
              </div>
              <div>
                <div className="font-medium text-text-1">API Reference</div>
                <div className="text-xs text-text-3">Endpoints & examples</div>
              </div>
            </Card>
          </Link>

          <div
            role="button"
            tabIndex={0}
            onClick={() => setShowKeyModal(true)}
            onKeyDown={(e) => e.key === 'Enter' && setShowKeyModal(true)}
            className="cursor-pointer"
          >
            <Card className="flex items-center gap-3 p-4 hover:border-accent/40 hover:shadow transition-all">
              <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center">
                <Key size={20} className="text-accent" />
              </div>
              <div>
                <div className="font-medium text-text-1">Get API Key</div>
                <div className="text-xs text-text-3">Free · 60 min/mo</div>
              </div>
            </Card>
          </div>

          <Link to="/jobs" className="no-underline">
            <Card className="flex items-center gap-3 p-4 hover:border-accent/40 hover:shadow transition-all cursor-pointer">
              <div className="w-10 h-10 rounded-lg bg-success/10 flex items-center justify-center">
                <List size={20} className="text-success" />
              </div>
              <div>
                <div className="font-medium text-text-1">Jobs</div>
                <div className="text-xs text-text-3">View & manage jobs</div>
              </div>
            </Card>
          </Link>

          <Link to="/dashboard" className="no-underline">
            <Card className="flex items-center gap-3 p-4 hover:border-accent/40 hover:shadow transition-all cursor-pointer">
              <div className="w-10 h-10 rounded-lg bg-warning/10 flex items-center justify-center">
                <LayoutDashboard size={20} className="text-warning" />
              </div>
              <div>
                <div className="font-medium text-text-1">Dashboard</div>
                <div className="text-xs text-text-3">Usage & overview</div>
              </div>
            </Card>
          </Link>
        </div>

        {/* Code examples */}
        <section className="mb-12">
          <h2 className="text-xl font-semibold text-text-1 mb-4">Quick start</h2>
          <div className="space-y-4">
            <div className="relative bg-surface-2 border border-divider rounded-xl overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 border-b border-divider bg-surface">
                <span className="text-xs font-medium text-text-3">Python</span>
                <CopyButton text={QUICKSTART_PYTHON} />
              </div>
              <pre className="p-4 text-xs font-mono text-text-2 overflow-auto whitespace-pre">
                {QUICKSTART_PYTHON}
              </pre>
            </div>
            <div className="relative bg-surface-2 border border-divider rounded-xl overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 border-b border-divider bg-surface">
                <span className="text-xs font-medium text-text-3">cURL</span>
                <CopyButton text={QUICKSTART_CURL} />
              </div>
              <pre className="p-4 text-xs font-mono text-text-2 overflow-auto whitespace-pre">
                {QUICKSTART_CURL}
              </pre>
            </div>
          </div>
        </section>

        {/* CTA */}
        <Card className="text-center py-8 bg-accent/5 border-accent/20">
          <h3 className="text-lg font-semibold text-text-1 mb-2">Ready to build?</h3>
          <p className="text-sm text-text-2 mb-4">
            Get your API key in 10 seconds. No credit card required.
          </p>
          <Button onClick={() => setShowKeyModal(true)}>
            <Key size={16} />
            Get API Key
          </Button>
        </Card>
      </div>

      <GetKeyModal
        open={showKeyModal}
        onClose={() => setShowKeyModal(false)}
      />
    </div>
  )
}
