/**
 * ResultViewer — kept for backwards compatibility.
 * The new chat-first layout lives in Jobs.tsx / ResultPanel.
 * Any direct links to /jobs/:videoId are handled by Jobs.tsx directly.
 */
import { useParams, Navigate } from 'react-router-dom'

export default function ResultViewer() {
  const { videoId } = useParams<{ videoId: string }>()
  if (!videoId) return <Navigate to="/jobs" replace />
  return <Navigate to={`/jobs/${videoId}`} replace />
}
