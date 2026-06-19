import { useState, useEffect } from 'react'
import { Download, X } from 'lucide-react'

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

/**
 * PWA install banner.
 *
 * Listens for the browser's `beforeinstallprompt` event.  On iOS (which
 * doesn't fire that event) shows a "Add to Home Screen" hint instead.
 * Dismissed state is persisted to localStorage so it doesn't reappear.
 */
export function InstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null)
  const [showIosHint, setShowIosHint]       = useState(false)
  const [dismissed, setDismissed]           = useState(
    () => localStorage.getItem('vi_install_dismissed') === '1'
  )

  useEffect(() => {
    if (dismissed) return

    const isIos     = /iphone|ipad|ipod/i.test(navigator.userAgent)
    const inStandalone = ('standalone' in navigator && (navigator as { standalone?: boolean }).standalone) ||
                         window.matchMedia('(display-mode: standalone)').matches

    if (inStandalone) return   // already installed

    if (isIos) {
      setShowIosHint(true)
      return
    }

    const handler = (e: Event) => {
      e.preventDefault()
      setDeferredPrompt(e as BeforeInstallPromptEvent)
    }
    window.addEventListener('beforeinstallprompt', handler)
    return () => window.removeEventListener('beforeinstallprompt', handler)
  }, [dismissed])

  const dismiss = () => {
    localStorage.setItem('vi_install_dismissed', '1')
    setDismissed(true)
    setDeferredPrompt(null)
    setShowIosHint(false)
  }

  const install = async () => {
    if (!deferredPrompt) return
    await deferredPrompt.prompt()
    const { outcome } = await deferredPrompt.userChoice
    if (outcome === 'accepted') dismiss()
    setDeferredPrompt(null)
  }

  if (dismissed) return null
  if (!deferredPrompt && !showIosHint) return null

  return (
    <div className="mx-3 mb-2 p-3 rounded-xl bg-accent/10 border border-accent/20">
      <div className="flex items-start gap-2">
        <Download size={14} className="text-accent mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-text-1">Install app</p>
          {showIosHint ? (
            <p className="text-[10px] text-text-3 mt-0.5">
              Tap <strong>Share</strong> → <strong>Add to Home Screen</strong> for offline access.
            </p>
          ) : (
            <p className="text-[10px] text-text-3 mt-0.5">
              Works offline. Submit from any device, see results on all.
            </p>
          )}
        </div>
        <button
          onClick={dismiss}
          className="p-0.5 text-text-3 hover:text-text-1 transition-colors shrink-0"
        >
          <X size={12} />
        </button>
      </div>
      {!showIosHint && deferredPrompt && (
        <button
          onClick={install}
          className="mt-2 w-full text-xs py-1.5 rounded-lg bg-accent text-white font-medium hover:bg-accent/90 transition-colors"
        >
          Install
        </button>
      )}
    </div>
  )
}
