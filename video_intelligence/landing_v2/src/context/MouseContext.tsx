import { createContext, useContext, useRef, useCallback, useEffect, type ReactNode } from 'react'

interface MouseState {
  x: number
  y: number
}

const MouseContext = createContext<React.MutableRefObject<MouseState> | null>(null)

export function MouseProvider({ children }: { children: ReactNode }) {
  const ref = useRef<MouseState>({ x: 0, y: 0 })

  const handleMove = useCallback((e: MouseEvent) => {
    ref.current = {
      x: (e.clientX / window.innerWidth) * 2 - 1,
      y: -(e.clientY / window.innerHeight) * 2 + 1,
    }
  }, [])

  useEffect(() => {
    window.addEventListener('mousemove', handleMove)
    return () => window.removeEventListener('mousemove', handleMove)
  }, [handleMove])

  return (
    <MouseContext.Provider value={ref}>
      {children}
    </MouseContext.Provider>
  )
}

export function useMouse() {
  const ctx = useContext(MouseContext)
  if (!ctx) throw new Error('useMouse must be used inside MouseProvider')
  return ctx
}
