import { column, Schema, Table } from '@powersync/web'

/**
 * Client-side PowerSync schema.
 *
 * Mirrors the server-side `jobs` and `chat_messages` Postgres tables.
 * PowerSync automatically adds an `id` TEXT column (the row primary key)
 * so we only declare the remaining columns here.
 *
 * Data flows: Postgres → PowerSync Service → local SQLite (via WebSocket sync)
 * Writes:     frontend calls API endpoints → Postgres → PowerSync → local SQLite
 */

const jobs = new Table(
  {
    user_id:          column.text,
    status:           column.text,
    input_filename:   column.text,
    input_type:       column.text,
    fps_used:         column.integer,
    duration_seconds: column.real,
    progress_percent: column.integer,
    current_stage:    column.text,
    queued_at:        column.text,
    started_at:       column.text,
    completed_at:     column.text,
    failed_at:        column.text,
    created_at:       column.text,
    summary:          column.text,
  },
  { indexes: { by_user: ['user_id'], by_created: ['created_at'] } }
)

const chat_messages = new Table(
  {
    video_id:   column.text,
    user_id:    column.text,
    role:       column.text,
    content:    column.text,
    created_at: column.text,
  },
  { indexes: { by_video: ['video_id'], by_user: ['user_id'] } }
)

const timeline_entries = new Table(
  {
    job_id:          column.text,
    user_id:         column.text,
    keyframe_index:  column.integer,
    timestamp_start: column.real,
    timestamp_end:   column.real,
    description:     column.text,
    detected_objects: column.text,
    camera_movement: column.text,
    confidence:      column.real,
  },
  { indexes: { by_job: ['job_id'], by_user: ['user_id'] } }
)

const library_messages = new Table(
  {
    user_id:    column.text,
    role:       column.text,
    content:    column.text,
    created_at: column.text,
  },
  { indexes: { by_user: ['user_id'], by_created: ['created_at'] } }
)

export const AppSchema = new Schema({ jobs, chat_messages, timeline_entries, library_messages })
export type Database = (typeof AppSchema)['types']
