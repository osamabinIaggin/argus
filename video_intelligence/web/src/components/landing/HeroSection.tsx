import React from 'react'
import { Play, Code2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '../ui/Button'

export function HeroSection() {
  return (
    <section className="max-w-6xl mx-auto px-6 pt-20 pb-16">
      <div className="grid lg:grid-cols-2 gap-14 items-center">

        {/* ── Left: copy ─────────────────────────────────────────────── */}
        <div className="text-center lg:text-left fade-up">
          <div className="inline-flex items-center gap-2 px-3 py-1 bg-accent/10 text-accent rounded-full text-sm font-medium mb-8">
            <span className="w-1.5 h-1.5 bg-accent rounded-full animate-pulse" />
            Now in beta
          </div>

          <h1 className="text-4xl md:text-5xl font-bold text-text-1 leading-tight tracking-tight mb-5">
            Turn any video into structured AI intelligence.
          </h1>

          <p className="text-lg text-text-2 leading-relaxed mb-10">
            Upload a video, get a timestamped timeline, full summary, and chat with it. Built for LLMs &amp; agents.
          </p>

          <Link to="/try">
            <Button size="lg" className="px-10 text-base">
              <Play size={20} />
              Try Video Intelligence
            </Button>
          </Link>

          <p className="text-sm text-text-3 mt-4">
            Free tier: 60 minutes/month · No credit card required
          </p>

          {/* Stats strip */}
          <div className="mt-10 flex flex-wrap justify-center lg:justify-start gap-x-6 gap-y-2 text-xs text-text-3">
            <span>⚡ Frame-by-frame keyframes</span>
            <span>🎙 Audio transcription</span>
            <span>🤖 Gemini 2.5 vision AI</span>
            <span>📦 REST API · JSON output</span>
          </div>

          {/* Developer link */}
          <div className="mt-10 pt-6 border-t border-divider">
            <p className="text-sm text-text-3 mb-2">Integrate video analysis into your AI?</p>
            <Link
              to="/developers"
              className="text-sm text-accent hover:underline font-medium"
            >
              For developers — REST API &amp; quickstart →
            </Link>
          </div>
        </div>

        {/* ── Right: JSON output preview ──────────────────────────────── */}
        <div className="hidden lg:block fade-up stagger" style={{ '--stagger': 3 } as React.CSSProperties}>
          <div className="rounded-2xl border border-divider shadow-2xl overflow-hidden bg-surface">
            {/* Window chrome */}
            <div className="flex items-center gap-3 px-4 py-3 border-b border-divider bg-surface-2">
              <div className="flex gap-1.5">
                <span className="w-3 h-3 rounded-full bg-error/40" />
                <span className="w-3 h-3 rounded-full bg-warning/40" />
                <span className="w-3 h-3 rounded-full bg-success/40" />
              </div>
              <div className="flex items-center gap-1.5 px-2.5 py-1 bg-surface rounded-md border border-divider text-xs text-text-3 font-mono ml-1">
                <Code2 size={11} />
                result.json
              </div>
              <div className="ml-auto">
                <span className="inline-flex items-center gap-1 text-xs text-success font-medium">
                  <span className="w-1.5 h-1.5 bg-success rounded-full animate-pulse" />
                  complete
                </span>
              </div>
            </div>

            {/* Syntax-highlighted JSON */}
            <pre className="p-5 text-[11.5px] font-mono leading-[1.75] overflow-auto max-h-[380px] text-text-2">
<JsonLine indent={0} type="brace-open" />{'\n'}
<JsonLine indent={1} key_="video_id" val='"vid_a3f8b2c1d4e5..."' vtype="string" />{'\n'}
<JsonLine indent={1} key_="summary" val='"Product demo: presenter guides through onboarding flow, highlighting key UI interactions and live data views."' vtype="string" />{'\n'}
<JsonLine indent={1} key_="timeline" val="[" vtype="array-open" />{'\n'}
<JsonLine indent={2} type="brace-open" />{'\n'}
<JsonLine indent={3} key_="timestamp_start" val='"0:00"' vtype="string" />{'\n'}
<JsonLine indent={3} key_="timestamp_end" val='"0:08"' vtype="string" />{'\n'}
<JsonLine indent={3} key_="description" val='"Title card fades in with animated logo. Clean white background, camera static."' vtype="string" />{'\n'}
<JsonLine indent={3} key_="detected_objects" val='["logo", "text", "background"]' vtype="array" />{'\n'}
<JsonLine indent={3} key_="camera_movement" val='"static"' vtype="string" />{'\n'}
<JsonLine indent={3} key_="scene_change" val="true" vtype="bool" last />{'\n'}
<JsonLine indent={2} type="brace-close" comma />{'\n'}
<JsonLine indent={2} type="brace-open" />{'\n'}
<JsonLine indent={3} key_="timestamp_start" val='"0:08"' vtype="string" />{'\n'}
<JsonLine indent={3} key_="timestamp_end" val='"0:23"' vtype="string" />{'\n'}
<JsonLine indent={3} key_="description" val='"Presenter sits at desk, opens laptop. Camera pans slowly to reveal dashboard UI with real-time charts."' vtype="string" />{'\n'}
<JsonLine indent={3} key_="detected_objects" val='["person", "laptop", "desk", "monitor"]' vtype="array" />{'\n'}
<JsonLine indent={3} key_="camera_movement" val='"slow_pan"' vtype="string" />{'\n'}
<JsonLine indent={3} key_="scene_change" val="false" vtype="bool" last />{'\n'}
<JsonLine indent={2} type="brace-close" />{'\n'}
<JsonLine indent={1} type="array-close" />{'\n'}
<JsonLine indent={0} type="brace-close" />
            </pre>
          </div>
        </div>

      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Micro syntax-highlight helper — no deps, just spans
// ---------------------------------------------------------------------------

interface JsonLineProps {
  indent?: number
  key_?: string
  val?: string
  vtype?: 'string' | 'bool' | 'number' | 'array' | 'array-open'
  type?: 'brace-open' | 'brace-close' | 'array-close'
  last?: boolean
  comma?: boolean
}

function JsonLine({ indent = 0, key_, val, vtype, type, last, comma }: JsonLineProps) {
  const pad = '  '.repeat(indent)

  if (type === 'brace-open')  return <><span className="text-text-3">{pad}{'{'}</span></>
  if (type === 'brace-close') return <><span className="text-text-3">{pad}{'}'}</span>{comma ? <span className="text-text-3">,</span> : null}</>
  if (type === 'array-close') return <><span className="text-text-3">{pad}{']'}</span></>

  const valNode = (() => {
    if (vtype === 'string')     return <span className="text-success">{val}</span>
    if (vtype === 'bool')       return <span className="text-info">{val}</span>
    if (vtype === 'number')     return <span className="text-warning">{val}</span>
    if (vtype === 'array-open') return <span className="text-text-3">{val}</span>
    if (vtype === 'array')      return <span className="text-text-2">{val}</span>
    return <span>{val}</span>
  })()

  return (
    <>
      <span className="text-text-3">{pad}</span>
      <span className="text-accent">"{key_}"</span>
      <span className="text-text-3">: </span>
      {valNode}
      {!last && <span className="text-text-3">,</span>}
    </>
  )
}
