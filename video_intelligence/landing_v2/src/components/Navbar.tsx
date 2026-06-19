import { useState } from 'react'
import { Video, Menu, X } from 'lucide-react'
import { urls } from '../config'

export function Navbar() {
  const [showModal, setShowModal] = useState(false)

  const navLinks = [
    { to: urls.try, label: 'Try it' },
    { to: urls.developers, label: 'For developers' },
    { to: urls.docs, label: 'Docs' },
  ]

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-bg/80 backdrop-blur-xl border-b border-divider">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <a href="/" className="flex items-center gap-2 font-semibold text-text-1">
          <Video size={22} className="text-accent" />
          <span>Video Intelligence</span>
        </a>

        <div className="hidden md:flex items-center gap-8 text-sm text-text-2">
          {navLinks.map(({ to, label }) => (
            <a
              key={to}
              href={to}
              className="hover:text-text-1 transition-colors"
            >
              {label}
            </a>
          ))}
        </div>

        <div className="hidden md:flex items-center gap-3">
          <a
            href={urls.try}
            className="px-4 py-2 rounded-lg text-sm font-medium text-text-2 hover:text-text-1 transition-colors"
          >
            Log in
          </a>
          <a
            href={urls.try}
            className="px-5 py-2.5 rounded-lg text-sm font-semibold bg-white text-bg hover:bg-text-2 hover:text-text-1 transition-colors"
          >
            Get started (for free)
          </a>
        </div>

        <button
          className="md:hidden p-2 text-text-2 hover:text-text-1"
          onClick={() => setShowModal(!showModal)}
        >
          {showModal ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* Mobile menu */}
      {showModal && (
        <div className="md:hidden border-t border-divider bg-bg-elevated p-4 flex flex-col gap-4">
          {navLinks.map(({ to, label }) => (
            <a
              key={to}
              href={to}
              className="text-text-2 hover:text-text-1 py-2"
              onClick={() => setShowModal(false)}
            >
              {label}
            </a>
          ))}
          <a
            href={urls.try}
            className="px-5 py-2.5 rounded-lg text-sm font-semibold bg-white text-bg text-center"
            onClick={() => setShowModal(false)}
          >
            Get started (for free)
          </a>
        </div>
      )}
    </nav>
  )
}
