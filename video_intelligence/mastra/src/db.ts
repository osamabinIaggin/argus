import pg from 'pg'
import { readFileSync } from 'fs'

const { Pool } = pg

function buildSsl(): pg.PoolConfig['ssl'] {
  const certPath = process.env.DB_SSL_CERT
  if (!certPath) return { rejectUnauthorized: false }
  try {
    return { ca: readFileSync(certPath).toString() }
  } catch {
    // Cert file not found — fall back to required-SSL without cert pinning
    return { rejectUnauthorized: false }
  }
}

export const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: buildSsl(),
  max: 5,
})

export interface TimelineRow {
  id: string
  job_id: string
  user_id: string
  keyframe_index: number
  timestamp_start: number
  timestamp_end: number
  description: string | null
  detected_objects: string | null
  camera_movement: string | null
  confidence: number | null
}
