import { useEffect, useState } from 'react'
import gsap from 'gsap'

interface LoadingScreenProps {
  onComplete: () => void
}

export function LoadingScreen({ onComplete }: LoadingScreenProps) {
  const [percent, setPercent] = useState(0)

  useEffect(() => {
    const tl = gsap.timeline({
      onComplete: () => {
        gsap.to('.loading-screen', { opacity: 0, duration: 0.5, onComplete })
      },
    })

    // Animate 0–100% with slot-machine style (we simulate with a simple counter)
    tl.to(
      {},
      {
        duration: 2.5,
        onUpdate: function () {
          const p = Math.min(100, Math.floor(this.progress() * 100))
          setPercent(p)
        },
        ease: 'power2.inOut',
      }
    )
  }, [onComplete])

  return (
    <div className="loading-screen fixed inset-0 z-50 bg-[#1E1E1E] flex flex-col items-center justify-center">
      <div className="text-[#FFFFFF] font-light text-6xl tabular-nums tracking-tighter">
        {String(percent).padStart(3, '0')}%
      </div>
      <div className="mt-2 text-[#FFFFFF]/60 text-sm tracking-widest uppercase">
        Loading
      </div>
    </div>
  )
}
