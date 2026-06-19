import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Video, Sun, Moon, Menu, X } from 'lucide-react'
import { Button } from '../ui/Button'
import { useAuth } from '../../context/AuthContext'
import { useTheme } from '../../context/ThemeContext'

export function Navbar() {
  const { accessToken } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const [mobileOpen, setMobileOpen] = useState(false)

  const close = () => setMobileOpen(false)

  return (
    <nav className="sticky top-0 z-40 bg-page/80 backdrop-blur-sm border-b border-divider">
      <div className="max-w-6xl mx-auto px-4 md:px-6 h-14 flex items-center justify-between">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2 font-semibold text-text-1 shrink-0">
          <Video size={20} className="text-accent" />
          <span>Video Intelligence</span>
        </Link>

        {/* Desktop nav links */}
        <div className="hidden md:flex items-center gap-6 text-sm text-text-2">
          <Link to="/try" className="hover:text-text-1 transition-colors">Try it</Link>
          <Link to="/docs" className="hover:text-text-1 transition-colors">Docs</Link>
          <Link to="/developers" className="hover:text-text-1 transition-colors">For developers</Link>
        </div>

        {/* Desktop right actions */}
        <div className="hidden md:flex items-center gap-2">
          <button
            onClick={toggleTheme}
            title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
            className="p-2 rounded-lg text-text-3 hover:text-text-1 hover:bg-surface-2 transition-colors"
          >
            {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
          </button>

          {accessToken ? (
            <Link to="/dashboard">
              <Button size="sm">Dashboard</Button>
            </Link>
          ) : (
            <>
              <Link to="/login">
                <Button size="sm" variant="secondary">Sign in</Button>
              </Link>
              <Link to="/register">
                <Button size="sm">Get started</Button>
              </Link>
            </>
          )}
        </div>

        {/* Mobile right: theme toggle + hamburger */}
        <div className="flex md:hidden items-center gap-1">
          <button
            onClick={toggleTheme}
            className="p-2 rounded-lg text-text-3 hover:text-text-1 hover:bg-surface-2 transition-colors"
          >
            {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
          </button>
          <button
            onClick={() => setMobileOpen((o) => !o)}
            className="p-2 rounded-lg text-text-2 hover:text-text-1 hover:bg-surface-2 transition-colors"
            aria-label="Toggle menu"
          >
            {mobileOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      {/* Mobile dropdown */}
      {mobileOpen && (
        <div className="md:hidden border-t border-divider bg-page/95 backdrop-blur-sm px-4 py-4 flex flex-col gap-1">
          <Link
            to="/try"
            onClick={close}
            className="px-3 py-2.5 rounded-lg text-sm text-text-2 hover:text-text-1 hover:bg-surface-2 transition-colors"
          >
            Try it
          </Link>
          <Link
            to="/docs"
            onClick={close}
            className="px-3 py-2.5 rounded-lg text-sm text-text-2 hover:text-text-1 hover:bg-surface-2 transition-colors"
          >
            Docs
          </Link>
          <Link
            to="/developers"
            onClick={close}
            className="px-3 py-2.5 rounded-lg text-sm text-text-2 hover:text-text-1 hover:bg-surface-2 transition-colors"
          >
            For developers
          </Link>

          <div className="border-t border-divider mt-2 pt-3 flex flex-col gap-2">
            {accessToken ? (
              <Link to="/dashboard" onClick={close}>
                <Button className="w-full">Dashboard</Button>
              </Link>
            ) : (
              <>
                <Link to="/login" onClick={close}>
                  <Button variant="secondary" className="w-full">Sign in</Button>
                </Link>
                <Link to="/register" onClick={close}>
                  <Button className="w-full">Get started</Button>
                </Link>
              </>
            )}
          </div>
        </div>
      )}
    </nav>
  )
}
