import { useStatus } from '@powersync/react'

/**
 * Tiny sync status indicator shown in the sidebar footer.
 * Green dot = synced live, amber = connecting, grey = offline/disabled.
 */
export function SyncStatus() {
  const status = useStatus()

  if (!status) return null

  const synced    = status.hasSynced === true
  const connected = status.connected === true

  const color = synced && connected
    ? 'bg-success'
    : connected
      ? 'bg-warning animate-pulse'
      : 'bg-text-3'

  const label = synced && connected
    ? 'Live sync'
    : connected
      ? 'Syncing…'
      : 'Offline'

  return (
    <div className="flex items-center gap-1.5 px-3 py-1">
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${color}`} />
      <span className="text-[10px] text-text-3">{label}</span>
    </div>
  )
}
