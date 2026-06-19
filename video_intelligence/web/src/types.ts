// ---------------------------------------------------------------------------
// API response types
// ---------------------------------------------------------------------------

export interface AnalyzeResponse {
  video_id: string
  status: string
  eta_seconds?: number
}

export interface StatusResponse {
  video_id: string
  status: 'queued' | 'processing' | 'complete' | 'failed'
  progress_percent: number
  current_stage?: string
  error?: string
}

export interface DetectedObject {
  label?: string
  confidence?: number
}

export interface KeyframeEntry {
  keyframe_id: number
  timestamp_start: string
  timestamp_end: string
  description: string
  camera_movement: string
  actions: string
  changes_from_previous: string
  detected_objects: string[]
  scene_change: boolean
  confidence: number
}

export interface VideoMetadata {
  duration_seconds: number
  original_fps: number
  processed_fps: number
  original_resolution: string
  processed_resolution: string
  total_frames_extracted: number
  keyframes_analyzed: number
  duplicates_removed: number
  processing_time_seconds: number
}

export interface VideoResult {
  video_id: string
  status: string
  metadata: VideoMetadata
  summary: string
  timeline: KeyframeEntry[]
}

export interface APIKeyInfo {
  key: string
  name: string
  plan: string
  is_active: boolean
  total_requests: number
  created_at: string
  last_used_at: string | null
}

export interface JobListItem {
  video_id: string
  status: 'queued' | 'processing' | 'complete' | 'failed'
  progress_percent: number
  submitted_at: string
  duration_seconds?: number
  summary?: string | null
}

// ---------------------------------------------------------------------------
// Plan info
// ---------------------------------------------------------------------------

export interface PlanInfo {
  name: string
  label: string
  minutes_per_month: number
  price_per_month: number
}

export const PLANS: Record<string, PlanInfo> = {
  free: { name: 'free', label: 'Free', minutes_per_month: 60, price_per_month: 0 },
  starter: { name: 'starter', label: 'Starter', minutes_per_month: 300, price_per_month: 19 },
  pro: { name: 'pro', label: 'Pro', minutes_per_month: 1500, price_per_month: 79 },
  enterprise: { name: 'enterprise', label: 'Enterprise', minutes_per_month: Infinity, price_per_month: -1 },
}
