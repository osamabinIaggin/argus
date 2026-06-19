import { NavLink } from 'react-router-dom'
import { Home, Plus, Video, Library } from 'lucide-react'

const tabs = [
  { to: '/dashboard',  label: 'Home',    icon: Home },
  { to: '/playground', label: 'Analyze', icon: Plus },
  { to: '/jobs',       label: 'Videos',  icon: Video },
  { to: '/library',    label: 'Library', icon: Library },
]

export function BottomNav() {
  return (
    <nav
      className="flex items-stretch bg-surface-2 border-t border-divider shrink-0"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      {tabs.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/jobs'}
          className={({ isActive }) =>
            [
              'flex-1 flex flex-col items-center justify-center pt-2 pb-1 gap-0.5 text-[10px] font-medium transition-colors',
              isActive ? 'text-accent' : 'text-text-3 hover:text-text-2',
            ].join(' ')
          }
        >
          {({ isActive }) => (
            <>
              <Icon size={20} strokeWidth={isActive ? 2.5 : 1.5} />
              <span>{label}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
