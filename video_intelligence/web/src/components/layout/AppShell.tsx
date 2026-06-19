import { useState, useEffect, type ReactNode } from 'react'
import { Menu, Plus, Video } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { BottomNav } from './BottomNav'
import { useNotifications } from '../../hooks/useNotifications'

interface AppShellProps {
  children: ReactNode
  fullBleed?: boolean
}

/** True when running as an installed PWA (standalone/fullscreen display mode). */
function isPwa(): boolean {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    window.matchMedia('(display-mode: fullscreen)').matches ||
    (navigator as unknown as { standalone?: boolean }).standalone === true
  )
}

export default function AppShell({ children, fullBleed }: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [pwa] = useState(isPwa)
  const { autoRegister } = useNotifications()

  // Silently refresh FCM token on every authenticated page load
  useEffect(() => { autoRegister() }, [autoRegister])

  return (
    <div className="flex h-[100dvh] w-full max-w-full bg-page overflow-hidden">
      {/* Desktop sidebar — always visible md+ */}
      <div className="hidden md:flex shrink-0">
        <Sidebar />
      </div>

      {/* Mobile sidebar drawer — only shown when opened in browser mode */}
      {sidebarOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setSidebarOpen(false)}
          />
          {/* Drawer panel */}
          <div className="relative z-10 flex animate-[slideInLeft_0.2s_ease-out]">
            <Sidebar onClose={() => setSidebarOpen(false)} />
          </div>
        </div>
      )}

      {/* Main area */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* Mobile top bar — hidden in PWA mode (bottom nav handles navigation) */}
        {!pwa && (
          <header className="md:hidden shrink-0 h-12 px-2 flex items-center justify-between border-b border-divider bg-surface-2">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-2 rounded-lg text-text-2 hover:text-text-1 hover:bg-surface transition-colors"
              aria-label="Open menu"
            >
              <Menu size={20} />
            </button>
            <Link to="/" className="flex items-center gap-2 font-semibold text-text-1 text-sm">
              <Video size={16} className="text-accent" />
              Video Intelligence
            </Link>
            <Link
              to="/playground"
              className="p-2 rounded-lg text-text-2 hover:text-text-1 hover:bg-surface transition-colors"
              aria-label="New analysis"
            >
              <Plus size={20} />
            </Link>
          </header>
        )}

        {/* PWA top bar — safe area padding for notch/Dynamic Island */}
        {pwa && (
          <div
            className="md:hidden shrink-0 bg-surface-2"
            style={{ height: 'env(safe-area-inset-top)' }}
          />
        )}

        {fullBleed ? (
          <main className="flex-1 overflow-hidden flex flex-col">{children}</main>
        ) : (
          <main className="flex-1 overflow-auto">
            <div className="max-w-5xl mx-auto px-4 md:px-6 py-6 md:py-8">
              {children}
            </div>
          </main>
        )}

        {/* Bottom navigation — only on mobile in PWA mode */}
        {pwa && <div className="md:hidden"><BottomNav /></div>}
      </div>
    </div>
  )
}
