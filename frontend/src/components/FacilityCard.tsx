import { Link } from 'react-router-dom'
import { formatCountdown, formatDateTime } from '../format'
import type { ApprovalStatus, Facility } from '../types'
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

export function FacilityCard({ facility, now }: FacilityCardProps) {
  const { current } = facility
  // Never show a calm posture next to a failed or stale source (contract: UI rules).
  const needsAttention = current?.confidence === 'low' || facility.source_health !== 'ok'
  // Unknown approval values from the backend fall back to a neutral chip instead of crashing.
  const approval = current ? (approvalLabels[current.approval_status] ?? approvalLabels.pending) : null

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
