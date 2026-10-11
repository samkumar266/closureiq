import { alertsFrom, alertTier, findInput, tierRank, type AlertTierName } from '../../alerts'
import { formatDateTime, formatTime } from '../../format'
import type { Recommendation } from '../../types'

type AlertListProps = {
  recommendation: Recommendation
  timeZone: string
}

// Tier decides the colour, and the tier is always written out too (never colour alone).
const tierStyles: Record<AlertTierName, { box: string; label: string }> = {
  warning: { box: 'border-red-700 bg-red-600 text-white', label: 'Warning' },
  watch: { box: 'border-amber-500 bg-amber-100 text-amber-950', label: 'Watch' },
  advisory: { box: 'border-yellow-400 bg-yellow-50 text-yellow-950', label: 'Advisory' },
}

// Active NWS alerts at the facility point, most serious first. Shown only when there are alerts.
export function AlertList({ recommendation, timeZone }: AlertListProps) {
  const input = findInput(recommendation, 'alert')
  const alerts = alertsFrom(input).sort((left, right) => tierRank[alertTier(left)] - tierRank[alertTier(right)])
  if (!input || alerts.length === 0) return null

  return (
    <section aria-label="Active NWS alerts" className="space-y-2">
      {alerts.map((alert, index) => {
        const tier = alertTier(alert)
        return (
          <article className={`rounded-xl border-2 px-4 py-3 ${tierStyles[tier].box}`} key={`${alert.event}-${index}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-bold">
                {tier === 'warning' ? '▲' : '△'} {alert.event}
              </h2>
              <span className="text-xs font-bold uppercase tracking-wide">
                {tierStyles[tier].label}
                {index === 0 && ' · drives the recommendation'}
              </span>
            </div>
            {/* USDA: alerts carry structured severity, certainty and urgency; show all three. */}
            <p className="mt-1 flex flex-wrap gap-1 text-xs">
              {(['severity', 'certainty', 'urgency'] as const).map(
                (field) =>
                  alert[field] && (
                    <span className="rounded bg-black/10 px-1.5 py-0.5" key={field}>
                      {field} {alert[field]}
                    </span>
                  ),
              )}
            </p>
            {alert.onset && alert.ends && (
              <p className="mt-1 text-sm">
                In effect {formatDateTime(alert.onset, timeZone)} to {formatDateTime(alert.ends, timeZone)}
              </p>
            )}
          </article>
        )
      })}
      <p className="text-xs text-slate-500">
        {input.source} · fetched {formatTime(input.fetched_at, timeZone)} · {input.snapshot_id}
      </p>
    </section>
  )
}
