import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'
import type { Facility } from '../types'
import { PostureChip } from './PostureChip'
import { SourceHealthDot } from './SourceHealthDot'

type FacilityCardProps = {
  facility: Facility
}

function formatCountdown(deadline: string | null, now: number) {
  if (!deadline) {
    return 'No decision required'
  }

  const remainingMilliseconds = new Date(deadline).getTime() - now
  if (remainingMilliseconds <= 0) {
    return 'Decision deadline passed'
  }

  const totalSeconds = Math.floor(remainingMilliseconds / 1_000)
  const hours = Math.floor(totalSeconds / 3_600)
  const minutes = Math.floor((totalSeconds % 3_600) / 60)
  const seconds = totalSeconds % 60

  return `${hours}h ${minutes}m ${seconds}s remaining`
}

export function FacilityCard({ facility }: FacilityCardProps) {
  const [now, setNow] = useState(Date.now)
  const { current } = facility
  const needsAttention = current.confidence === 'low' || facility.source_health === 'missing'

  useEffect(() => {
    const intervalId = window.setInterval(() => setNow(Date.now()), 1_000)
    return () => window.clearInterval(intervalId)
  }, [])

  return (
    <Link
      aria-label={`View ${facility.name}`}
      className="block rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-slate-400 hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
      to={`/facilities/${facility.facility_id}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h2 className="text-lg font-semibold text-slate-950">{facility.name}</h2>
        <PostureChip posture={current.posture} />
      </div>
      <p className="mt-3 text-sm text-slate-700">{current.headline}</p>
      {needsAttention && (
        <p className="mt-3 rounded-md bg-red-100 px-3 py-2 text-sm font-semibold text-red-900">
          Attention required: recommendation confidence or source evidence is limited.
        </p>
      )}
      <p className="mt-4 text-sm text-slate-700">
        <span className="font-medium text-slate-950">Confidence: </span>
        {current.confidence}
      </p>
      <p aria-live="polite" className="mt-2 text-sm text-slate-700">
        <span className="font-medium text-slate-950">Deadline: </span>
        {formatCountdown(current.decision_deadline, now)}
      </p>
      <div className="mt-4">
        <SourceHealthDot sourceHealth={facility.source_health} />
      </div>
    </Link>
  )
}
