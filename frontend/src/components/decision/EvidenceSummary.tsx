import { Link } from 'react-router-dom'
import { alertsFrom, alertTier, findInput, tierRank } from '../../alerts'
import { formatNumber, formatTime } from '../../format'
import { thresholdName } from '../../thresholds'
import type { Recommendation, RecommendationInput, ThresholdCrossed, ThresholdNotCrossed } from '../../types'

type EvidenceSummaryProps = {
  recommendation: Recommendation
  timeZone: string
  // Link to the stored evidence and logs (the decision record). Omitted on the record page itself.
  recordHref?: string
}

const ALERT_CHECKS = new Set(['T1', 'T2', 'T3'])

// How a value was obtained, in words a facility manager reads: forecast or measured, and where.
function measuredHow(input: RecommendationInput | undefined) {
  if (!input) return 'value'
  const source = input.source.toLowerCase()
  if (source.includes('observations')) {
    const station = (input.value as { station?: string } | null)?.station
    return `measured${station ? ` at ${station} station` : ''} (last hour)`
  }
  if (source.includes('forecast')) return 'forecast peak'
  if (source.includes('usgs')) return 'measured river level'
  return input.label
}

const amount = (value: string | number, unit?: string) =>
  typeof value === 'number' ? `${formatNumber(value)}${unit ? ` ${unit}` : ''}` : value

// Plain names for the evidence sources, shown with their fetch time and snapshot id.
function sourceName(input: RecommendationInput) {
  const source = input.source.toLowerCase()
  if (source.includes('alert')) return 'NWS active alerts'
  if (source.includes('forecast grid')) return 'NWS forecast (wind, ice, snow)'
  if (source.includes('observations')) return input.label
  return input.label
}

function Check({ ok, title, detail, tooltip }: { ok: boolean; title: string; detail: string; tooltip: string }) {
  return (
    <li className="flex gap-2 text-sm" title={tooltip}>
      <span aria-hidden="true" className={ok ? 'text-emerald-700' : 'text-slate-400'}>
        {ok ? '✓' : '✗'}
      </span>
      <span>
        <span className="font-medium text-slate-900">{title}</span>
        <span className="text-slate-600"> · {detail}</span>
        <span className="sr-only">{ok ? ' (met)' : ' (not met)'}</span>
      </span>
    </li>
  )
}

export function EvidenceSummary({ recommendation, timeZone, recordHref }: EvidenceSummaryProps) {
  const inputById = (id: string) => recommendation.inputs.find((input) => input.id === id)
  const alertsInput = findInput(recommendation, 'alert')
  const alerts = alertsFrom(alertsInput).sort((a, b) => tierRank[alertTier(a)] - tierRank[alertTier(b)])
  const [drivingAlert, ...otherAlerts] = alerts

  const alertChecks: { threshold: ThresholdCrossed | ThresholdNotCrossed; ok: boolean }[] = [
    ...recommendation.thresholds_crossed.filter((t) => ALERT_CHECKS.has(t.id)).map((threshold) => ({ threshold, ok: true })),
    ...recommendation.thresholds_not_crossed.filter((t) => ALERT_CHECKS.has(t.id)).map((threshold) => ({ threshold, ok: false })),
  ].sort((a, b) => a.threshold.id.localeCompare(b.threshold.id))
  const numericCrossed = recommendation.thresholds_crossed.filter((t) => !ALERT_CHECKS.has(t.id))
  const numericNotCrossed = recommendation.thresholds_not_crossed.filter((t) => !ALERT_CHECKS.has(t.id))
  const sources = recommendation.inputs.filter((input) => !input.source.toLowerCase().includes('hourly'))

  return (
    <section aria-label="Evidence" className="rounded-xl bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-slate-950">What drove this recommendation</h2>
        {recordHref && (
          <Link
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-semibold text-slate-800 hover:bg-slate-100"
            title="Stored raw evidence, evaluation chain, decision and replay"
            to={recordHref}
          >
            Evidence log &amp; replay →
          </Link>
        )}
      </div>

      {drivingAlert ? (
        <div className="mt-3 rounded-lg border border-slate-200 p-3">
          <p className="font-semibold text-slate-950">NWS {drivingAlert.event}</p>
          <ul className="mt-2 space-y-1">
            {alertChecks.map(({ threshold, ok }) => (
              <Check
                detail={
                  threshold.id === 'T1'
                    ? `${drivingAlert.event} is a ${String(threshold.actual)}`
                    : `${threshold.id === 'T2' ? 'severity' : 'certainty'} ${String(threshold.actual)}`
                }
                key={threshold.id}
                ok={ok}
                title={thresholdName(threshold.id)}
                tooltip={`Policy rule ${threshold.id}`}
              />
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-2 text-sm text-slate-600">No active NWS alert at the facility.</p>
      )}

      {numericCrossed.length > 0 ? (
        <ul className="mt-3 space-y-2">
          {numericCrossed.map((threshold) => (
            <li className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm" key={`${threshold.id}-${threshold.input_id}`} title={`Policy rule ${threshold.id}`}>
              <p className="font-semibold text-slate-950">✓ {thresholdName(threshold.id)}</p>
              <p className="mt-1 text-slate-800">
                {measuredHow(inputById(threshold.input_id))}: <strong>{amount(threshold.actual, threshold.unit)}</strong>
                {threshold.margin !== undefined && threshold.margin !== null && (
                  <span className="font-semibold text-red-800">, {amount(threshold.margin, threshold.unit)} over</span>
                )}
              </p>
              {threshold.anchor && (
                <p className="mt-1 text-xs text-slate-600">
                  Why this cutoff:{' '}
                  {threshold.anchor_url ? (
                    <a className="underline" href={threshold.anchor_url} rel="noreferrer" target="_blank">
                      {threshold.anchor}
                    </a>
                  ) : (
                    threshold.anchor
                  )}
                </p>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
          No measured or forecast wind, ice or river value has crossed its threshold.
        </p>
      )}

      {(numericNotCrossed.length > 0 || otherAlerts.length > 0) && (
        <>
          <h3 className="mt-6 font-bold text-slate-950">Also checked</h3>
          <ul className="mt-2 space-y-1">
            {numericNotCrossed.map((threshold) => (
              <Check
                detail={`${measuredHow(inputById(threshold.input_id))} ${amount(threshold.actual, threshold.unit)}${
                  threshold.distance !== undefined && threshold.distance !== null
                    ? `, ${amount(threshold.distance, threshold.unit)} below`
                    : ''
                }`}
                key={`${threshold.id}-${threshold.input_id}`}
                ok={false}
                title={thresholdName(threshold.id)}
                tooltip={`Policy rule ${threshold.id}`}
              />
            ))}
            {otherAlerts.map((alert, index) => (
              <li className="text-sm text-slate-700" key={`${alert.event}-${index}`}>
                <span className="font-medium text-slate-900">NWS {alert.event}</span>
                {[alert.severity, alert.certainty].filter(Boolean).length > 0 &&
                  ` · ${[alert.severity, alert.certainty].filter(Boolean).join(', ')}`}
                {' · '}not the alert driving the recommendation
              </li>
            ))}
          </ul>
        </>
      )}

      <h3 className="mt-6 text-sm font-bold text-slate-950">Sources</h3>
      <ul className="mt-1 space-y-0.5 text-xs text-slate-500">
        {sources.map((input) => (
          <li key={input.id}>
            {sourceName(input)} · fetched {formatTime(input.fetched_at, timeZone)} · {input.snapshot_id}
            {input.stale && <span className="ml-1 font-semibold text-amber-700">STALE</span>}
          </li>
        ))}
      </ul>
    </section>
  )
}
