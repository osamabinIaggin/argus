import { useState, useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Plus, ArrowRight, Activity, Clock, Layers } from 'lucide-react'
import { api } from '../api/client'
import { useJobs } from '../hooks/useJobs'
import { useApiKey } from '../context/ApiKeyContext'
import { Card } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { ProgressBar } from '../components/ui/ProgressBar'
import { PLANS, type APIKeyInfo } from '../types'

function useAnimatedCounter(target: number, duration = 800): number {
  const [count, setCount] = useState(0)
  const prev = useRef(0)
  useEffect(() => {
    if (target === prev.current) return
    const start = prev.current
    const delta = target - start
    const startTime = performance.now()
    const step = (now: number) => {
      const elapsed = Math.min((now - startTime) / duration, 1)
      const eased = 1 - Math.pow(1 - elapsed, 3) // ease-out cubic
      setCount(Math.round(start + delta * eased))
      if (elapsed < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
    prev.current = target
  }, [target, duration])
  return count
}

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return 'never'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs} hr ago`
  return `${Math.floor(hrs / 24)} d ago`
}

export default function Dashboard() {
  const { apiKey } = useApiKey()
  const { data: keyInfo } = useQuery<APIKeyInfo>({
    queryKey: ['keyInfo'],
    queryFn: () => api.getKeyInfo(),
    enabled: !!apiKey,
  })
  const { data: jobs = [] } = useJobs()

  const plan = keyInfo ? PLANS[keyInfo.plan] ?? PLANS['free'] : PLANS['free']
  const activeJobs = jobs.filter((j) => j.status === 'processing' || j.status === 'queued').length
  const totalMinutes = jobs
    .filter((j) => j.status === 'complete' && j.duration_seconds)
    .reduce((acc, j) => acc + (j.duration_seconds ?? 0) / 60, 0)

  const usedMinutes = Math.round(totalMinutes)
  const planMinutes = plan.minutes_per_month
  const usedPct = planMinutes === Infinity ? 0 : Math.min(100, (usedMinutes / planMinutes) * 100)

  const animatedRequests = useAnimatedCounter(keyInfo?.total_requests ?? 0)
  const animatedActive = useAnimatedCounter(activeJobs)
  const animatedMinutes = useAnimatedCounter(usedMinutes)

  const recentJobs = jobs.slice(0, 5)
  const navigate = useNavigate()

  return (
    <div className="flex flex-col gap-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-1">Dashboard</h1>
          <p className="text-sm text-text-2 mt-1">
            {keyInfo?.name ?? '—'} · <span className="capitalize">{plan.label}</span>
          </p>
        </div>
        <Link to="/playground">
          <Button>
            <Plus size={16} />
            Analyze new video
          </Button>
        </Link>
      </div>

      {/* Stats row — each card navigates to the relevant page */}
      <div className="grid grid-cols-3 gap-4">
        <Link to="/keys" className="fade-up stagger" style={{ '--stagger': 0 } as React.CSSProperties}>
          <Card className="card-hover hover:border-text-3 hover:shadow transition-all cursor-pointer">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-accent/10 flex items-center justify-center">
                <Activity size={18} className="text-accent" />
              </div>
              <div>
                <div className="text-xs text-text-3 mb-0.5">Requests (all time)</div>
                <div className="text-xl font-semibold text-text-1 tabular-nums">
                  {animatedRequests}
                </div>
              </div>
            </div>
          </Card>
        </Link>

        <Link to="/jobs" className="fade-up stagger" style={{ '--stagger': 1 } as React.CSSProperties}>
          <Card className="card-hover hover:border-text-3 hover:shadow transition-all cursor-pointer">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-warning/10 flex items-center justify-center">
                <Layers size={18} className="text-warning" />
              </div>
              <div>
                <div className="text-xs text-text-3 mb-0.5">Active jobs</div>
                <div className="text-xl font-semibold text-text-1 tabular-nums">{animatedActive}</div>
              </div>
            </div>
          </Card>
        </Link>

        <Link to="/keys" className="fade-up stagger" style={{ '--stagger': 2 } as React.CSSProperties}>
          <Card className="card-hover hover:border-text-3 hover:shadow transition-all cursor-pointer">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-info/10 flex items-center justify-center">
                <Clock size={18} className="text-info" />
              </div>
              <div>
                <div className="text-xs text-text-3 mb-0.5">Minutes processed</div>
                <div className="text-xl font-semibold text-text-1 tabular-nums">{animatedMinutes}</div>
              </div>
            </div>
          </Card>
        </Link>
      </div>

      {/* Usage meter */}
      <Card>
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-sm font-medium text-text-1">{plan.label} plan</div>
            <div className="text-xs text-text-2 mt-0.5">
              {planMinutes === Infinity
                ? 'Unlimited minutes'
                : `${usedMinutes} / ${planMinutes} minutes used`}
            </div>
          </div>
          <Link to="/keys" className="text-xs text-accent hover:underline">
            Manage plan
          </Link>
        </div>
        <ProgressBar value={usedPct} />
      </Card>

      {/* Recent jobs */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-text-1">Recent jobs</h2>
          <Link to="/jobs" className="text-xs text-accent hover:underline flex items-center gap-1">
            View all <ArrowRight size={12} />
          </Link>
        </div>

        {recentJobs.length === 0 ? (
          <Card>
            <div className="text-center py-8 text-text-3 text-sm">
              No jobs yet.{' '}
              <Link to="/playground" className="text-accent hover:underline">
                Analyze your first video →
              </Link>
            </div>
          </Card>
        ) : (
          <Card padding={false}>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-divider">
                  <th className="text-left px-5 py-3 text-xs font-medium text-text-3">Video ID</th>
                  <th className="text-left px-5 py-3 text-xs font-medium text-text-3">Status</th>
                  <th className="text-left px-5 py-3 text-xs font-medium text-text-3">Progress</th>
                  <th className="text-left px-5 py-3 text-xs font-medium text-text-3">Submitted</th>
                </tr>
              </thead>
              <tbody>
                {recentJobs.map((job, i) => (
                  <tr
                    key={job.video_id}
                    onClick={() => navigate(`/jobs/${job.video_id}`)}
                    className={[
                      'hover:bg-surface-2 transition-colors cursor-pointer',
                      i < recentJobs.length - 1 ? 'border-b border-divider' : '',
                    ].join(' ')}
                  >
                    <td className="px-5 py-3">
                      <span className="font-mono text-xs text-accent">
                        {job.video_id.slice(0, 18)}…
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      <Badge status={job.status} />
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <ProgressBar value={job.progress_percent} className="w-20" />
                        <span className="text-xs text-text-3">{job.progress_percent}%</span>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-xs text-text-3">
                      {relativeTime(job.submitted_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </div>
  )
}
