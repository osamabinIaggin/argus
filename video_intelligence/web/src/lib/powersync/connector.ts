import type { AbstractPowerSyncDatabase, PowerSyncBackendConnector } from '@powersync/web'
import { api } from '../../api/client'

/**
 * PowerSync BackendConnector for Video Intelligence.
 *
 * fetchCredentials() — called by PowerSync when it needs a token.
 *   Gets a short-lived JWT from our backend (/v1/powersync/token) that
 *   PowerSync uses to authenticate WebSocket sync streams.
 *
 * uploadData() — called when local SQLite mutations need to reach the server.
 *   All our writes go through dedicated API endpoints (not direct table writes),
 *   so we drain the upload queue as a no-op.  The data flows the other way:
 *   server writes → Postgres → PowerSync Service → local SQLite.
 */
export class VideoIntelligenceConnector implements PowerSyncBackendConnector {
  async fetchCredentials() {
    const { token, powersync_url } = await api.getPowerSyncToken()
    return { endpoint: powersync_url, token }
  }

  async uploadData(database: AbstractPowerSyncDatabase) {
    // Drain any queued local mutations (should be empty — we never write to
    // PowerSync-managed tables directly from the client).
    const tx = await database.getNextCrudTransaction()
    if (tx) {
      await tx.complete()
    }
  }
}
