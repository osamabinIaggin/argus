import { useEffect, useRef } from 'react'

export function useLenis() {
  const lenisRef = useRef<import('lenis').default | null>(null)

  useEffect(() => {
    import('lenis').then(({ default: Lenis }) => {
      const lenis = new Lenis({
        duration: 1.2,
        easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      })
      lenisRef.current = lenis

      function raf(time: number) {
        lenis.raf(time)
        requestAnimationFrame(raf)
      }
      requestAnimationFrame(raf)

      return () => {
        lenis.destroy()
        lenisRef.current = null
      }
    })
  }, [])

  return lenisRef
}
