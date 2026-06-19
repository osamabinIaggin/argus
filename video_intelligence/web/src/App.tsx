import { createBrowserRouter, RouterProvider, Navigate, Outlet } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from './context/AuthContext'
import { ApiKeyProvider } from './context/ApiKeyContext'
import { ThemeProvider } from './context/ThemeContext'
import { PowerSyncProvider } from './context/PowerSyncProvider'
import AppShell from './components/layout/AppShell'
import Landing from './pages/Landing'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import TryPage from './pages/TryPage'
import DevelopersPage from './pages/DevelopersPage'
import Dashboard from './pages/Dashboard'
import Playground from './pages/Playground'
import Jobs from './pages/Jobs'
import KeysPage from './pages/KeysPage'
import DocsPage from './pages/DocsPage'
import Library from './pages/Library'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
})

/**
 * Guards routes that require a logged-in session.
 *
 * While the auth state is being rehydrated from localStorage (isLoading),
 * renders nothing to avoid a flash-redirect on refresh.  Once resolved,
 * redirects unauthenticated users to /login.
 */
function ProtectedRoute() {
  const { accessToken, isLoading } = useAuth()

  if (isLoading) return null

  // Also check localStorage: login() writes there synchronously before the
  // React state update propagates, preventing a flash-redirect on navigate().
  if (!accessToken && !localStorage.getItem('vi_access_token')) return <Navigate to="/login" replace />

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  )
}

function ProtectedChatRoute() {
  const { accessToken, isLoading } = useAuth()
  if (isLoading) return null
  if (!accessToken && !localStorage.getItem('vi_access_token')) return <Navigate to="/login" replace />
  return (
    <AppShell fullBleed>
      <Outlet />
    </AppShell>
  )
}

/**
 * Redirects already-logged-in users away from /login and /register.
 * Prevents showing auth pages to users with an active session.
 */
function GuestOnlyRoute({ children }: { children: React.ReactNode }) {
  const { accessToken, isLoading } = useAuth()
  if (isLoading) return null
  if (accessToken) return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

const router = createBrowserRouter([
  // Public routes
  { path: '/',           element: <Landing /> },
  { path: '/try',        element: <TryPage /> },
  { path: '/developers', element: <DevelopersPage /> },
  { path: '/docs',       element: <DocsPage /> },

  // Auth routes — redirect to dashboard if already logged in
  {
    path: '/login',
    element: (
      <GuestOnlyRouteWrapper>
        <LoginPage />
      </GuestOnlyRouteWrapper>
    ),
  },
  {
    path: '/register',
    element: (
      <GuestOnlyRouteWrapper>
        <RegisterPage />
      </GuestOnlyRouteWrapper>
    ),
  },

  // Protected routes — standard padded layout
  {
    element: <ProtectedRouteWrapper />,
    children: [
      { path: '/dashboard',  element: <Dashboard /> },
      { path: '/playground', element: <Playground /> },
      { path: '/keys',       element: <KeysPage /> },
    ],
  },
  // Protected routes — full-bleed chat layout (no padding/max-width wrapper)
  {
    element: <ProtectedChatRouteWrapper />,
    children: [
      { path: '/jobs',          element: <Jobs /> },
      { path: '/jobs/:videoId', element: <Jobs /> },
      { path: '/library',       element: <Library /> },
    ],
  },
])

// Wrappers give the route components access to AuthContext (which is above
// RouterProvider in the tree).
function ProtectedRouteWrapper() {
  return <ProtectedRoute />
}
function ProtectedChatRouteWrapper() {
  return <ProtectedChatRoute />
}
function GuestOnlyRouteWrapper({ children }: { children: React.ReactNode }) {
  return <GuestOnlyRoute>{children}</GuestOnlyRoute>
}

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <PowerSyncProvider>
            <ApiKeyProvider>
              <RouterProvider router={router} />
            </ApiKeyProvider>
          </PowerSyncProvider>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
