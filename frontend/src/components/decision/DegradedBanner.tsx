import { formatDuration } from '../../format'
import type { Recommendation, SourceStatus } from '../../types'

type DegradedBannerProps = {
  recommendation: Recommendation
  sources: SourceStatus[]
}

// Contract rule: if confidence is low or evidence is missing, name the source and its age, loudly.
export function DegradedBanner({ recommendation, sources }: DegradedBannerProps) {
  const { missing_evidence: missing, confidence } = recommendation
  const badSources = sources.filter(
    (source) => source.status !== 'fresh' && !missing.some((item) => item.source === source.source),
  )

  if (confidence.level !== 'low' && missing.length === 0 && badSources.length === 0) {
    return null
  }

  return (
    <section aria-label="Degraded evidence" className="rounded-xl border-2 border-red-600 bg-red-50 p-5" role="alert">
      <h2 className="text-lg font-bold text-red-900">Degraded evidence: this is not an all-clear</h2>
      <ul className="mt-2 space-y-1 text-sm text-red-900">
        {missing.map((item) => (
          <li key={`missing-${item.source}`}>
            <strong>{item.source}</strong>: {item.reason}
            {item.last_good_age_minutes !== null && (
              <>
                {' '}
                (last good data {formatDuration(item.last_good_age_minutes * 60)} old, limit{' '}
                {formatDuration(item.max_age_minutes * 60)})
              </>
            )}
          </li>
        ))}
        {badSources.map((source) => (
          <li key={`source-${source.source}`}>
            <strong>{source.source}</strong> is {source.status}
            {source.age_seconds !== null && <> ({formatDuration(source.age_seconds)} old)</>}
          </li>
        ))}
        {missing.length === 0 && badSources.length === 0 && <li>Confidence is low: {confidence.reasons.join('; ')}</li>}
      </ul>
    </section>
  )
}
