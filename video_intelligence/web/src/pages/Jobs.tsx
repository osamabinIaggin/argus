import { useParams, useNavigate } from 'react-router-dom'
import { Video } from 'lucide-react'
import { ResultPanel } from '../components/results/ResultPanel'

export default function Jobs() {
  const { videoId } = useParams<{ videoId?: string }>()
  const navigate    = useNavigate()

  return (
    <div className="flex-1 overflow-hidden flex flex-col">
      {videoId ? (
        <ResultPanel videoId={videoId} />
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center px-6 fade-up">
          <div className="w-14 h-14 rounded-2xl bg-accent/10 flex items-center justify-center">
            <Video size={24} className="text-accent" />
          </div>
          <div>
            <p className="text-sm font-medium text-text-1">Select a video from the sidebar</p>
            <p className="text-xs text-text-3 mt-1">
              Or{' '}
              <button
                onClick={() => navigate('/playground')}
                className="text-accent hover:underline"
              >
                analyze a new video →
              </button>
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
