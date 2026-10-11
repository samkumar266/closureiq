import { Link } from 'react-router-dom'
import { formatCountdown, formatDateTime } from '../format'
import type { AlertTier, ApprovalStatus, Facility } from '../types'
import { PostureChip } from './PostureChip'
import { SourceHealthDot } from './SourceHealthDot'

type FacilityCardProps = {
  facility: Facility
  // Simulated-clock time in ms, passed from the Watchlist so every card ticks together.
  now: number
}

const approvalLabels: Record<ApprovalStatus, { label: string; className: string }> = {
  not_required: { label: 'No approval needed', className: 'bg-slate-100 text-slate-700' },
  pending: { label: 'Awaiting approval', className: 'bg-amber-100 text-amber-900' },
  approved: { label: 'Approved', className: 'bg-emerald-100 text-emerald-800' },
  rejected: { label: 'Rejected', className: 'bg-slate-200 text-slate-800' },
  overridden: { label: 'Overridden', className: 'bg-blue-100 text-blue-800' },
  unresolved: { label: 'UNRESOLVED', className: 'bg-red-100 text-red-900' },
}

const tierStyles: Record<AlertTier, string> = {
  warning: 'bg-red-600 text-white',
  watch: 'bg-amber-100 text-amber-900',
  advisory: 'bg-sky-100 text-sky-900',
  none: '',
}

export function FacilityCard({ facility, now }: FacilityCardProps) {
  const { current } = facility
  // Never show a calm posture next to a failed or stale source (contract: UI rules).
  const needsAttention = current?.confidence === 'low' || facility.source_health !== 'ok'
  // Unknown approval values from the backend fall back to a neutral chip instead of crashing.
  const approval = current ? (approvalLabels[current.approval_status] ?? approvalLabels.pending) : null
  // A non-normal posture still waiting for an approver needs a decision now.
  const decisionNeeded = current?.approval_status === 'pending' && current.posture !== 'normal_operations'
  const { top_alert: topAlert } = facility

  return (
    <Link
      aria-label={`View ${facility.name}`}
      className="block rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-slate-400 hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
      to={`/facilities/${facility.facility_id}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h2 className="text-lg font-semibold text-slate-950">{facility.name}</h2>
        {current ? (
          <PostureChip posture={current.posture} />
        ) : (
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-sm font-semibold text-slate-700">
            Not evaluated
          </span>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {facility.highest_alert_tier !== 'none' && (
          <span className={`rounded px-2 py-0.5 text-xs font-bold uppercase ${tierStyles[facility.highest_alert_tier]}`}>
            NWS {facility.highest_alert_tier}
          </span>
        )}
        {topAlert && (
          <span className="text-xs font-medium text-slate-700">
            {topAlert.event}
            {topAlert.severity && ` · ${topAlert.severity}`}
            {topAlert.certainty && ` · ${topAlert.certainty}`}
          </span>
        )}
        {decisionNeeded && (
          <span className="rounded bg-amber-400 px-2 py-0.5 text-xs font-bold text-slate-950">Decision needed</span>
        )}
      </div>
      <p className="mt-3 line-clamp-3 text-sm text-slate-700">
        {current ? current.headline : 'No evaluation yet. Open the facility to run one.'}
      </p>
      {needsAttention && (
        <p className="mt-3 rounded-md bg-red-100 px-3 py-2 text-sm font-semibold text-red-900">
          {facility.source_health !== 'ok'
            ? `Attention required: weather source is ${facility.source_health === 'missing' ? 'missing' : 'stale'}.`
            : 'Attention required: recommendation confidence is low.'}
        </p>
      )}
      {current && (
        <>
          <p className="mt-4 text-sm text-slate-700">
            <span className="font-medium text-slate-950">Confidence: </span>
            {current.confidence}
          </p>
          <p className="mt-2 text-sm text-slate-700">
            <span className="font-medium text-slate-950">Deadline: </span>
            {current.decision_deadline ? formatCountdown(current.decision_deadline, now) : 'No decision required'}
            {current.decision_deadline && (
              <span className="block text-xs text-slate-500">
                by {formatDateTime(current.decision_deadline, facility.location.timezone)}
              </span>
            )}
          </p>
        </>
      )}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <SourceHealthDot sourceHealth={facility.source_health} />
        {approval && (
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${approval.className}`}>
            {approval.label}
          </span>
        )}
      </div>
    </Link>
  )
}
