import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'

interface ApiKeyContextValue {
  apiKey: string | null
  setApiKey: (key: string) => void
  clearApiKey: () => void
}

const ApiKeyContext = createContext<ApiKeyContextValue | null>(null)

const STORAGE_KEY = 'vi_api_key'

export function ApiKeyProvider({ children }: { children: ReactNode }) {
  const [apiKey, setApiKeyState] = useState<string | null>(() =>
    localStorage.getItem(STORAGE_KEY)
  )

  const setApiKey = useCallback((key: string) => {
    localStorage.setItem(STORAGE_KEY, key)
    setApiKeyState(key)
  }, [])

  const clearApiKey = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    setApiKeyState(null)
  }, [])

  return (
    <ApiKeyContext.Provider value={{ apiKey, setApiKey, clearApiKey }}>
      {children}
    </ApiKeyContext.Provider>
  )
}

export function useApiKey(): ApiKeyContextValue {
  const ctx = useContext(ApiKeyContext)
  if (!ctx) throw new Error('useApiKey must be used inside ApiKeyProvider')
  return ctx
}
