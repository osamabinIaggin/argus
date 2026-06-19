import { useState } from 'react'
import { Check } from 'lucide-react'
import { Button } from '../ui/Button'
import { GetKeyModal } from './GetKeyModal'

const plans = [
  {
    name: 'Free',
    price: 0,
    minutes: 60,
    features: ['60 min/month', '5 FPS max', 'Community support', 'API access'],
    recommended: false,
    plan: 'free',
  },
  {
    name: 'Starter',
    price: 19,
    minutes: 300,
    features: ['300 min/month', '10 FPS max', 'Email support', 'API access', 'Job history'],
    recommended: true,
    plan: 'starter',
  },
  {
    name: 'Pro',
    price: 79,
    minutes: 1500,
    features: ['1,500 min/month', '30 FPS max', 'Priority support', 'API access', 'Job history', 'Webhooks'],
    recommended: false,
    plan: 'pro',
  },
  {
    name: 'Enterprise',
    price: null,
    minutes: null,
    features: ['Unlimited minutes', 'Custom FPS', 'Dedicated support', 'SLA', 'On-prem available'],
    recommended: false,
    plan: 'enterprise',
  },
]

export function PricingSection() {
  const [showModal, setShowModal] = useState(false)

  return (
    <>
      <section id="pricing" className="max-w-6xl mx-auto px-6 py-20">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold text-text-1 mb-3">Simple pricing</h2>
          <p className="text-text-2">Start free. Scale as you grow.</p>
        </div>

        <div className="grid md:grid-cols-4 gap-4">
          {plans.map((p) => (
            <div
              key={p.name}
              className={[
                'relative rounded-xl border p-5 flex flex-col',
                p.recommended
                  ? 'border-accent shadow-md bg-surface ring-2 ring-accent/20'
                  : 'border-divider bg-surface shadow-sm',
              ].join(' ')}
            >
              {p.recommended && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 bg-accent text-white text-xs font-semibold rounded-full">
                  Recommended
                </div>
              )}

              <div className="mb-4">
                <div className="text-sm font-semibold text-text-2 mb-1">{p.name}</div>
                {p.price === null ? (
                  <div className="text-2xl font-bold text-text-1">Custom</div>
                ) : (
                  <div className="flex items-baseline gap-1">
                    <span className="text-2xl font-bold text-text-1">${p.price}</span>
                    <span className="text-sm text-text-2">/mo</span>
                  </div>
                )}
                {p.minutes && (
                  <div className="text-xs text-text-3 mt-1">{p.minutes} minutes/month</div>
                )}
              </div>

              <ul className="flex-1 flex flex-col gap-2 mb-5">
                {p.features.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-text-2">
                    <Check size={13} className="text-success shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>

              {p.name === 'Enterprise' ? (
                <Button variant="secondary" className="w-full" size="sm">
                  Contact us
                </Button>
              ) : (
                <Button
                  variant={p.recommended ? 'primary' : 'secondary'}
                  className="w-full"
                  size="sm"
                  onClick={() => setShowModal(true)}
                >
                  Get started
                </Button>
              )}
            </div>
          ))}
        </div>
      </section>

      <GetKeyModal open={showModal} onClose={() => setShowModal(false)} />
    </>
  )
}
