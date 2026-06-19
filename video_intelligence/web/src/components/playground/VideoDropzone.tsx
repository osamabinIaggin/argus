import { useCallback, useState } from 'react'
import { Upload, FileVideo } from 'lucide-react'

const ACCEPTED = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
const ACCEPT_STRING = 'video/mp4,video/quicktime,video/x-msvideo,video/x-matroska,video/webm'

interface VideoDropzoneProps {
  onFile: (file: File) => void
}

export function VideoDropzone({ onFile }: VideoDropzoneProps) {
  const [dragging, setDragging] = useState(false)

  const handleFile = useCallback(
    (file: File) => {
      const ext = '.' + file.name.split('.').pop()?.toLowerCase()
      if (!ACCEPTED.includes(ext)) return
      onFile(file)
    },
    [onFile]
  )

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
    e.target.value = ''
  }

  return (
    <label
      className={[
        'flex flex-col items-center justify-center gap-3 cursor-pointer',
        'rounded-xl border-2 border-dashed px-6 py-10 transition-colors',
        dragging
          ? 'border-accent bg-accent/5'
          : 'border-divider bg-surface-2 hover:border-text-3 hover:bg-surface',
      ].join(' ')}
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <div className="w-12 h-12 rounded-full bg-accent/10 flex items-center justify-center">
        {dragging ? (
          <Upload size={22} className="text-accent" />
        ) : (
          <FileVideo size={22} className="text-accent" />
        )}
      </div>
      <div className="text-center">
        <p className="text-sm font-medium text-text-1">Drop a video here</p>
        <p className="text-xs text-text-3 mt-0.5">or click to browse</p>
        <p className="text-xs text-text-3 mt-1">{ACCEPTED.join(', ')} · max 500 MB</p>
      </div>
      <input type="file" accept={ACCEPT_STRING} className="sr-only" onChange={onInputChange} />
    </label>
  )
}
