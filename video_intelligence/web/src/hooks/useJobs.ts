import { useQuery as usePowerSyncQuery, useStatus } from '@powersync/react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { JobListItem } from '../types'

interface JobRow {
  id: string
  status: string
  progress_percent: number
  created_at: string
  duration_seconds: number | null
  summary: string | null
}

function mapRow(r: JobRow): JobListItem {
  return {
    video_id:         r.id,
    status:           (r.status as JobListItem['status']) ?? 'queued',
    progress_percent: r.progress_percent ?? 0,
    submitted_at:     r.created_at,
    duration_seconds: r.duration_seconds ?? undefined,
    summary:          r.summary ?? null,
  }
}

/**
 * Returns the user's job list.
 *
 * When PowerSync is synced (hasSynced = true): reads from the local SQLite
 * replica — instant, offline-capable, reactive (re-renders on any change
 * without polling).
 *
 * When PowerSync is not connected or not yet synced: falls back to the
 * REST polling strategy (every 5 s while any job is active).
 */
export function useJobs() {
  const psStatus = useStatus()
  const hasSynced = psStatus?.hasSynced === true

  // PowerSync reactive query — rerenders automatically on any change
  const { data: psRows = [] } = usePowerSyncQuery<JobRow>(
    'SELECT id, status, progress_percent, created_at, duration_seconds, summary ' +
    'FROM jobs ORDER BY created_at DESC'
  )

  // Polling fallback — disabled once PowerSync has synced
  const pollingQuery = useQuery<JobListItem[]>({
    queryKey: ['jobs'],
    queryFn:  () => api.listJobs(),
    staleTime: 10_000,
    enabled:   !hasSynced,
    refetchInterval: (query) => {
      if (hasSynced) return false
      const jobs = query.state.data
      if (!jobs) return false
      const hasActive = jobs.some(
        (j) => j.status === 'processing' || j.status === 'queued'
      )
      return hasActive ? 5000 : false
    },
  })

  if (hasSynced) {
    return {
      data:      psRows.map(mapRow),
      isLoading: false,
      isError:   false,
    }
  }

  return pollingQuery
}
