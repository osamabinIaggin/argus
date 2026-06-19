import { useState, useEffect } from 'react'

/**
 * useState backed by localStorage. Value survives page navigation and reload.
 * Pass a serialiser/deserialiser for non-string values (default: JSON).
 */
export function useLocalStorage<T>(
  key: string,
  initialValue: T,
): [T, (value: T | ((prev: T) => T)) => void] {
  const [state, setState] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key)
      if (raw === null) return initialValue
      return JSON.parse(raw) as T
    } catch {
      return initialValue
    }
  })

  useEffect(() => {
    try {
      if (state === null || state === undefined) {
        localStorage.removeItem(key)
      } else {
        localStorage.setItem(key, JSON.stringify(state))
      }
    } catch {
      /* storage full or private mode — fail silently */
    }
  }, [key, state])

  return [state, setState]
}
