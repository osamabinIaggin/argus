import { useQuery as usePowerSyncQuery, useStatus } from '@powersync/react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { api } from '../api/client'
import type { StatusResponse } from '../types'

interface JobStatusRow {
  id: string
  status: string
  progress_percent: number
  current_stage: string | null
}

/**
 * Returns the current status of a single job.
 *
 * When PowerSync is synced: reads from the local SQLite replica — instant,
 * reactive, no polling. The status row updates in real-time as the worker
 * writes progress to Postgres and PowerSync syncs it down.
 *
 * When PowerSync is not connected: falls back to REST polling every 2 s.
 */
export function useJobStatus(videoId: string | null, enabled = true) {
  const queryClient = useQueryClient()
  const psStatus    = useStatus()
  const hasSynced   = psStatus?.hasSynced === true

  // PowerSync reactive query
  const { data: psRows = [] } = usePowerSyncQuery<JobStatusRow>(
    'SELECT id, status, progress_percent, current_stage FROM jobs WHERE id = ?',
    videoId ? [videoId] : ['__none__']
  )
  const psRow = psRows[0] ?? null

  // Polling fallback
  const pollingQuery = useQuery<StatusResponse>({
    queryKey: ['status', videoId],
    queryFn:  () => api.getStatus(videoId!),
    enabled:  !!videoId && enabled && !hasSynced,
    refetchInterval: (query) => {
      if (hasSynced) return false
      const status = query.state.data?.status
      if (!status || status === 'complete' || status === 'failed') return false
      return 2000
    },
    staleTime: 0,
  })

  // When a job finishes, refresh the sidebar jobs list (polling path only)
  useEffect(() => {
    const status = hasSynced
      ? psRow?.status
      : pollingQuery.data?.status
    if (status === 'complete' || status === 'failed') {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    }
  }, [hasSynced, psRow?.status, pollingQuery.data?.status, queryClient])

  if (hasSynced && videoId) {
    const status = (psRow?.status ?? 'queued') as StatusResponse['status']
    return {
      data: {
        video_id:         videoId,
        status,
        progress_percent: psRow?.progress_percent ?? 0,
        current_stage:    psRow?.current_stage ?? undefined,
        error:            undefined,
      } satisfies StatusResponse,
      isLoading: false,
      isError:   false,
    }
  }

  return pollingQuery
}
