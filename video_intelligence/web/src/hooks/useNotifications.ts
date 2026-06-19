import { useState, useEffect, useCallback } from 'react'
import { app, VAPID_KEY, FCM_CONFIGURED } from '../firebase'
import { api } from '../api/client'

export type NotifState = 'unsupported' | 'idle' | 'loading' | 'granted' | 'denied'

/**
 * Manages FCM push notification permission and token registration.
 *
 * - `state`            — current permission status
 * - `requestPermission` — call this when the user clicks "Notify me"
 * - `autoRegister`    — call this on app load to silently register if already granted
 */
export function useNotifications() {
  const [state, setState] = useState<NotifState>('idle')

  // Detect support on mount
  useEffect(() => {
    if (!FCM_CONFIGURED || !('Notification' in window) || !('serviceWorker' in navigator)) {
      setState('unsupported')
    } else if (Notification.permission === 'granted') {
      setState('granted')
    } else if (Notification.permission === 'denied') {
      setState('denied')
    }
  }, [])

  const _getAndRegisterToken = useCallback(async (): Promise<boolean> => {
    if (!app) return false
    try {
      const { isSupported, getMessaging, getToken } = await import('firebase/messaging')
      if (!(await isSupported())) return false

      const messaging = getMessaging(app)
      const token = await getToken(messaging, { vapidKey: VAPID_KEY })
      if (!token) return false

      await api.registerFcmToken(token)
      return true
    } catch (err) {
      console.warn('FCM token registration failed:', err)
      return false
    }
  }, [])

  /** Explicit opt-in: shows the browser permission prompt if needed, then registers. */
  const requestPermission = useCallback(async (): Promise<boolean> => {
    if (!FCM_CONFIGURED || state === 'unsupported') return false
    setState('loading')
    try {
      const permission = await Notification.requestPermission()
      if (permission !== 'granted') {
        setState('denied')
        return false
      }
      const ok = await _getAndRegisterToken()
      setState(ok ? 'granted' : 'denied')
      return ok
    } catch {
      setState('denied')
      return false
    }
  }, [state, _getAndRegisterToken])

  /** Silent auto-register — call on app load if permission is already granted. */
  const autoRegister = useCallback(async () => {
    if (!FCM_CONFIGURED || Notification.permission !== 'granted') return
    await _getAndRegisterToken()
  }, [_getAndRegisterToken])

  return { state, requestPermission, autoRegister }
}
