import { Video } from 'lucide-react'
import { urls } from '../config'

export function Footer() {
  return (
    <footer className="border-t border-divider py-8">
      <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-text-2 text-sm">
          <Video size={16} className="text-accent" />
          <span className="font-medium">Video Intelligence</span>
        </div>
        <div className="flex items-center gap-6 text-sm text-text-2">
          <a href={urls.try} className="hover:text-text-1 transition-colors">
            Try it
          </a>
          <a href={urls.docs} className="hover:text-text-1 transition-colors">
            Docs
          </a>
          <a href={urls.developers} className="hover:text-text-1 transition-colors">
            For developers
          </a>
        </div>
        <div className="text-sm text-text-3">© 2025 Video Intelligence</div>
      </div>
    </footer>
  )
}
