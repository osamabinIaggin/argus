import { createTool } from '@mastra/core/tools'
import { z } from 'zod'
import { pool } from './db.js'

/**
 * Full-text search across timeline_entries for a specific user.
 * Returns matching keyframes with their job context (job summary + filename).
 */
export const searchTimelineTool = createTool({
  id: 'search_timeline',
  description:
    'Search across analysed videos by visual terms — what the camera sees, not names or labels. ' +
    'Pass multiple comma-separated terms to broaden the search (e.g. "apartment, suit, comedian"). ' +
    'Optionally pass job_id to search within a specific video identified by list_videos.',
  inputSchema: z.object({
    query: z.string().describe(
      'Visual search terms — describe what the camera sees. Comma-separate multiple terms to OR them ' +
      '(e.g. "man in suit, apartment, couch"). Do NOT use celebrity names or show titles here.'
    ),
    user_id: z.string().describe('The authenticated user ID'),
    job_id: z.string().optional().describe('Limit search to a specific video job ID (from list_videos)'),
    limit: z.number().optional().default(15).describe('Max results to return'),
  }),
  execute: async ({ context }) => {
    const { query, user_id, job_id, limit } = context

    // Split comma-separated terms into individual ILIKE clauses (OR logic)
    const terms = query.split(',').map((t) => t.trim()).filter((t) => t.length >= 2)
    if (terms.length === 0) {
      return { results: [], message: 'Query too short — provide at least one search term (2+ characters).' }
    }

    // Build parameterised query dynamically
    const params: (string | number)[] = [user_id]
    const termClauses = terms.map((term) => {
      const idx = params.length + 1
      params.push(`%${term}%`)
      return `(te.description ILIKE $${idx} OR te.detected_objects ILIKE $${idx} OR j.summary ILIKE $${idx})`
    })
    const whereTerms = termClauses.length > 0 ? `AND (${termClauses.join(' OR ')})` : ''

    let jobFilter = ''
    if (job_id) {
      params.push(job_id)
      jobFilter = `AND te.job_id = $${params.length}`
    }

    params.push(limit)
    const limitParam = `$${params.length}`

    const { rows } = await pool.query<{
      id: string
      job_id: string
      timestamp_start: number
      timestamp_end: number
      description: string
      detected_objects: string
      camera_movement: string
      job_summary: string
      input_filename: string
    }>(
      `SELECT
         te.id, te.job_id, te.timestamp_start, te.timestamp_end,
         te.description, te.detected_objects, te.camera_movement,
         j.summary AS job_summary, j.input_filename
       FROM timeline_entries te
       JOIN jobs j ON j.id = te.job_id
       WHERE te.user_id = $1
         ${whereTerms}
         ${jobFilter}
       ORDER BY te.job_id, te.keyframe_index
       LIMIT ${limitParam}`,
      params
    )

    if (rows.length === 0) {
      return { results: [], message: `No keyframes found matching "${query}".` }
    }

    return {
      results: rows.map((r) => ({
        job_id: r.job_id,
        filename: r.input_filename,
        job_summary: r.job_summary,
        timestamp: `${r.timestamp_start.toFixed(1)}s–${r.timestamp_end.toFixed(1)}s`,
        description: r.description,
        objects: r.detected_objects,
        camera: r.camera_movement,
      })),
    }
  },
})

/**
 * List the user's videos with their summaries.
 */
export const listVideosTool = createTool({
  id: 'list_videos',
  description:
    'List all videos you have analysed, with their summaries and durations. ' +
    'Use this to get an overview of your video library before searching.',
  inputSchema: z.object({
    user_id: z.string().describe('The authenticated user ID'),
  }),
  execute: async ({ context }) => {
    const { user_id } = context

    const { rows } = await pool.query<{
      id: string
      input_filename: string
      duration_seconds: number
      summary: string
      completed_at: string
    }>(
      `SELECT id, input_filename, duration_seconds, summary, completed_at
       FROM jobs
       WHERE user_id = $1 AND status = 'complete'
       ORDER BY completed_at DESC`,
      [user_id]
    )

    return {
      videos: rows.map((r) => ({
        id: r.id,
        filename: r.input_filename,
        duration: r.duration_seconds ? `${Math.round(r.duration_seconds)}s` : null,
        summary: r.summary,
        analysed_at: r.completed_at,
      })),
      count: rows.length,
    }
  },
})
