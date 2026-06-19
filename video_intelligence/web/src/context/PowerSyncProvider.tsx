import { type ReactNode, useEffect, useRef } from 'react'
import { PowerSyncContext } from '@powersync/react'
import { powerSyncDb } from '../lib/powersync/db'
import { VideoIntelligenceConnector } from '../lib/powersync/connector'
import { useAuth } from './AuthContext'

const connector = new VideoIntelligenceConnector()

/**
 * Provides the PowerSync database to the component tree.
 *
 * Connects whenever the user is authenticated. The actual PowerSync URL and
 * JWT come from the backend (/v1/powersync/token) via fetchCredentials() —
 * no client-side env var needed.
 *
 * If the server has PowerSync disabled (returns 503), the connector's
 * fetchCredentials() will throw and PowerSync will stay disconnected,
 * falling back gracefully to REST polling in useJobs / useJobStatus.
 */
export function PowerSyncProvider({ children }: { children: ReactNode }) {
  const { accessToken } = useAuth()
  const connectedRef = useRef(false)

  useEffect(() => {
    if (!accessToken) {
      if (connectedRef.current) {
        powerSyncDb.disconnect()
        connectedRef.current = false
      }
      return
    }

    if (!connectedRef.current) {
      powerSyncDb.connect(connector)
      connectedRef.current = true
    }

    return () => {
      powerSyncDb.disconnect()
      connectedRef.current = false
    }
    // Re-connect when access token changes (user switches account, token refreshes)
  }, [accessToken])

  return (
    <PowerSyncContext.Provider value={powerSyncDb}>
      {children}
    </PowerSyncContext.Provider>
  )
}
