import type { ClockMode } from '../hooks/useServerClock'
import type { DataMode } from '../types'

type StatusBadgesProps = {
  dataMode: DataMode
  fromFixture: boolean
  now: number
  clockMode: ClockMode
  speed: number
}

// Data mode and clock badges. Shown on every screen so replay or sample data is never unlabelled.
export function StatusBadges({ dataMode, fromFixture, now, clockMode, speed }: StatusBadgesProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {fromFixture && (
        <span className="rounded-full bg-slate-200 px-3 py-1 text-sm font-bold text-slate-700">SAMPLE DATA</span>
      )}
      <span
        className={`rounded-full px-3 py-1 text-sm font-bold ${
          dataMode === 'live' ? 'bg-emerald-100 text-emerald-800' : 'bg-violet-100 text-violet-800'
        }`}
      >
        {dataMode.toUpperCase()}
      </span>
      <time aria-label="Current time" className="font-mono text-sm text-slate-700">
        {new Date(now).toLocaleTimeString([], { timeZoneName: 'short' })}
      </time>
      {clockMode === 'simulated' && (
        <span className="rounded-full bg-amber-100 px-3 py-1 text-sm font-bold text-amber-900">
          SIMULATED {speed}x
        </span>
      )}
    </div>
  )
}
