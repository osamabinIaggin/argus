import { Link } from 'react-router-dom'
import { Video } from 'lucide-react'
import { CopyButton } from '../components/ui/CopyButton'

interface CodeBlockProps {
  lang: string
  code: string
}

function CodeBlock({ lang, code }: CodeBlockProps) {
  return (
    <div className="relative bg-surface-2 border border-divider rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-divider bg-surface">
        <span className="text-xs font-medium text-text-3">{lang}</span>
        <CopyButton text={code} />
      </div>
      <pre className="p-4 text-xs font-mono text-text-2 overflow-auto whitespace-pre">{code}</pre>
    </div>
  )
}

interface EndpointProps {
  method: 'GET' | 'POST' | 'DELETE'
  path: string
  description: string
  auth?: boolean
  children: React.ReactNode
}

const methodColors = {
  GET: 'bg-info/10 text-info',
  POST: 'bg-success/10 text-success',
  DELETE: 'bg-error/10 text-error',
}

function Endpoint({ method, path, description, auth = true, children }: EndpointProps) {
  return (
    <div className="border border-divider rounded-xl overflow-hidden mb-6">
      <div className="flex items-center gap-3 px-5 py-4 bg-surface border-b border-divider">
        <span className={['px-2 py-0.5 text-xs font-bold rounded font-mono', methodColors[method]].join(' ')}>
          {method}
        </span>
        <code className="text-sm font-mono text-text-1">{path}</code>
        {!auth && (
          <span className="ml-auto text-xs text-text-3 bg-surface-2 px-2 py-0.5 rounded">
            No auth
          </span>
        )}
      </div>
      <div className="px-5 py-4 bg-surface">
        <p className="text-sm text-text-2 mb-4">{description}</p>
        {children}
      </div>
    </div>
  )
}

export default function DocsPage() {
  return (
    <div className="min-h-screen bg-page">
      {/* Minimal nav */}
      <nav className="sticky top-0 z-40 bg-page/80 backdrop-blur-sm border-b border-divider">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 font-semibold text-text-1">
            <Video size={18} className="text-accent" />
            Video Intelligence
          </Link>
          <div className="flex items-center gap-4 text-sm text-text-2">
            <Link to="/try" className="hover:text-text-1 transition-colors">Try it</Link>
            <Link to="/developers" className="hover:text-text-1 transition-colors">For developers</Link>
            <Link to="/dashboard" className="text-accent hover:underline font-medium">
              Dashboard →
            </Link>
          </div>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-6 py-12">
        <h1 className="text-3xl font-bold text-text-1 mb-2">API Reference</h1>
        <p className="text-text-2 mb-10">
          Base URL: <code className="font-mono text-sm bg-surface-2 px-1.5 py-0.5 rounded">{window.location.origin}</code>
        </p>

        {/* Authentication */}
        <section className="mb-12">
          <h2 className="text-xl font-semibold text-text-1 mb-4">Authentication</h2>
          <p className="text-sm text-text-2 mb-4">
            Pass your API key as a Bearer token in the <code className="font-mono bg-surface-2 px-1 rounded text-xs">Authorization</code> header.
          </p>
          <CodeBlock
            lang="HTTP"
            code={`Authorization: Bearer vi_live_<your-key>`}
          />
        </section>

        {/* Endpoints */}
        <section>
          <h2 className="text-xl font-semibold text-text-1 mb-6">Endpoints</h2>

          <Endpoint
            method="POST"
            path="/v1/analyze"
            auth
            description="Queue a video for async processing. Returns video_id immediately. Poll /v1/status/:id for progress."
          >
            <CodeBlock
              lang="cURL"
              code={`curl -X POST https://your-server.com/v1/analyze \\
  -H "Authorization: Bearer vi_live_..." \\
  -F "file=@video.mp4" \\
  -F "fps=5"`}
            />
            <div className="mt-4">
              <CodeBlock
                lang="Python"
                code={`import requests

r = requests.post("https://your-server.com/v1/analyze",
    headers={"Authorization": "Bearer vi_live_..."},
    files={"file": open("video.mp4", "rb")},
    data={"fps": 5})
print(r.json())  # {"video_id": "vid_...", "status": "queued"}`}
              />
            </div>
          </Endpoint>

          <Endpoint
            method="POST"
            path="/v1/analyze/sync"
            auth
            description="Synchronous pipeline — runs inline and returns full JSON. Only for short videos (≤ 60 s)."
          >
            <CodeBlock
              lang="cURL"
              code={`curl -X POST https://your-server.com/v1/analyze/sync \\
  -H "Authorization: Bearer vi_live_..." \\
  -F "file=@short_clip.mp4"`}
            />
          </Endpoint>

          <Endpoint
            method="GET"
            path="/v1/status/{video_id}"
            auth
            description="Poll the processing status of a queued video."
          >
            <CodeBlock
              lang="cURL"
              code={`curl -H "Authorization: Bearer vi_live_..." \\
  https://your-server.com/v1/status/vid_4c9003c3...

# Response:
# {
#   "video_id": "vid_4c9003c3...",
#   "status": "processing",
#   "progress_percent": 65,
#   "current_stage": "vision_model"
# }`}
            />
          </Endpoint>

          <Endpoint
            method="GET"
            path="/v1/result/{video_id}"
            auth
            description="Fetch the full structured JSON output for a completed video."
          >
            <CodeBlock
              lang="cURL"
              code={`curl -H "Authorization: Bearer vi_live_..." \\
  https://your-server.com/v1/result/vid_4c9003c3...`}
            />
          </Endpoint>

          <Endpoint
            method="DELETE"
            path="/v1/result/{video_id}"
            auth
            description="Delete a job's result and all associated files."
          >
            <CodeBlock
              lang="cURL"
              code={`curl -X DELETE -H "Authorization: Bearer vi_live_..." \\
  https://your-server.com/v1/result/vid_4c9003c3...`}
            />
          </Endpoint>

          <Endpoint
            method="POST"
            path="/v1/keys"
            auth={false}
            description="Create a new API key. No auth required. Returns the key once — save it immediately."
          >
            <CodeBlock
              lang="cURL"
              code={`curl -X POST https://your-server.com/v1/keys \\
  -H "Content-Type: application/json" \\
  -d '{"name": "Alice", "plan": "free"}'

# Response:
# {"key": "vi_live_...", "name": "Alice", "plan": "free"}`}
            />
          </Endpoint>

          <Endpoint
            method="GET"
            path="/v1/keys/me"
            auth
            description="Return info about the authenticated key (key masked, metadata included)."
          >
            <CodeBlock
              lang="cURL"
              code={`curl -H "Authorization: Bearer vi_live_..." \\
  https://your-server.com/v1/keys/me`}
            />
          </Endpoint>

          <Endpoint
            method="GET"
            path="/v1/jobs"
            auth
            description="List all analysis jobs associated with your key."
          >
            <CodeBlock
              lang="cURL"
              code={`curl -H "Authorization: Bearer vi_live_..." \\
  https://your-server.com/v1/jobs`}
            />
          </Endpoint>
        </section>

        {/* Response shape */}
        <section className="mt-12">
          <h2 className="text-xl font-semibold text-text-1 mb-4">Result shape</h2>
          <CodeBlock
            lang="JSON"
            code={`{
  "video_id": "vid_4c9003c3...",
  "status": "complete",
  "metadata": {
    "duration_seconds": 105.82,
    "processed_resolution": "640x1390",
    "keyframes_analyzed": 367,
    "duplicates_removed": 162
  },
  "summary": "The video opens with…",
  "timeline": [
    {
      "keyframe_id": 1,
      "timestamp_start": "0:00.00",
      "timestamp_end": "0:00.80",
      "description": "A vibrant tropical mural…",
      "camera_movement": "static",
      "actions": "",
      "detected_objects": ["surfboard"],
      "scene_change": true,
      "confidence": 0.0
    }
  ]
}`}
          />
        </section>
      </div>
    </div>
  )
}
