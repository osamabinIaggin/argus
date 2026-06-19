import { PowerSyncDatabase } from '@powersync/web'
import { AppSchema } from './schema'

/**
 * Singleton PowerSync database instance.
 *
 * This is a local SQLite database (via WASM) that is kept in sync with the
 * Postgres backend by the PowerSync Service.  It is always queryable — even
 * offline — because all reads hit the local copy.
 *
 * The database is connected to the sync service when the user is authenticated
 * (see PowerSyncProvider).  If VITE_POWERSYNC_URL is not set the provider
 * skips connect(), leaving the database in local-only mode (still queryable,
 * just not synced — the app falls back to polling hooks automatically).
 */
export const powerSyncDb = new PowerSyncDatabase({
  schema: AppSchema,
  database: { dbFilename: 'video-intelligence.db' },
})
