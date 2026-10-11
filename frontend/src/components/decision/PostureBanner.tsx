import { formatCountdown, formatDateTime, formatTime } from '../../format'
import { postureTheme } from '../../theme'
import type { Recommendation } from '../../types'
import { PostureChip } from '../PostureChip'

type PostureBannerProps = {
  recommendation: Recommendation
  timeZone: string
  now: number
}

// One line saying what the posture means in practice, built only from engine parameters.
function postureSummary({ posture, parameters }: Recommendation, timeZone: string) {
  switch (posture) {
    case 'delayed_arrival':
      return parameters.delay_until
        ? `Delay arrival until ${formatDateTime(parameters.delay_until, timeZone)}`
        : 'Delay arrival'
    case 'early_dismissal':
      return parameters.dismiss_at
        ? `Dismiss early at ${formatDateTime(parameters.dismiss_at, timeZone)}`
        : 'Dismiss early'
    case 'closure':
      return parameters.closed_from && parameters.closed_until
        ? `Closed ${formatDateTime(parameters.closed_from, timeZone)} to ${formatTime(parameters.closed_until, timeZone)}`
        : 'Facility closed'
    case 'unscheduled_leave_or_telework':
      return 'Unscheduled leave or telework for staff who can'
    case 'normal_operations':
      return parameters.monitoring === 'elevated' ? 'Normal operations with elevated monitoring' : 'Normal operations'
  }
}

export function PostureBanner({ recommendation, timeZone, now }: PostureBannerProps) {
  const { color } = postureTheme[recommendation.posture]
  const { decision_deadline: deadline, parameters } = recommendation

  return (
    <section
      aria-label="Recommendation"
      className="rounded-xl border-l-8 bg-white p-6 shadow-sm"
      style={{ borderLeftColor: color }}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-slate-500">The engine recommends</p>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <PostureChip posture={recommendation.posture} />
            <h2 className="text-2xl font-bold text-slate-950">{postureSummary(recommendation, timeZone)}</h2>
          </div>
          {recommendation.held_by_hysteresis && (
            <p className="mt-2 text-sm text-slate-700">
              Held at this posture: the latest reading points to{' '}
              <strong>{postureTheme[recommendation.raw_posture].label.toLowerCase()}</strong>, but a downgrade needs two
              evaluations 15 minutes apart.
            </p>
          )}
        </div>
        <div className="text-right">
          <p className="text-sm font-medium text-slate-500">Decision deadline</p>
          {deadline ? (
            <>
              <p className="mt-1 font-mono text-lg font-semibold text-slate-950">{formatCountdown(deadline, now)}</p>
              <p className="text-sm text-slate-600">by {formatDateTime(deadline, timeZone)}</p>
            </>
          ) : (
            <p className="mt-1 text-lg font-semibold text-slate-700">No decision required</p>
          )}
        </div>
      </div>

      {recommendation.safety_instruction && (
        <p className="mt-4 rounded-md bg-red-600 px-4 py-3 font-semibold text-white">
          Safety instruction: {recommendation.safety_instruction}
        </p>
      )}

      <p className="mt-4 text-xs text-slate-500">
        Evaluation {recommendation.evaluation_id} at {formatDateTime(recommendation.evaluated_at, timeZone)}
        {parameters.next_update && <> · next update {formatTime(parameters.next_update, timeZone)}</>} ·{' '}
        {recommendation.policy_version}
      </p>
    </section>
  )
}
