import type { ClockMode, ClockStatus } from '../hooks/useServerClock'
import type { DataMode } from '../types'

type StatusBadgesProps = {
  dataMode: DataMode
  // DEPRECATED(closureiq): sample-data fallback removed, so there is no SAMPLE DATA state any more.
  // fromFixture: boolean
  now: number
  clockMode: ClockMode
  clockStatus: ClockStatus
  speed: number
}

// Data mode and clock badges. Shown on every screen so replay data or a missing server clock is never hidden.
export function StatusBadges({ dataMode, now, clockMode, clockStatus, speed }: StatusBadgesProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* DEPRECATED(closureiq) START: SAMPLE DATA badge for the removed fixture fallback. */}
      {/* {fromFixture && ( */}
      {/*   <span className="rounded-full bg-slate-200 px-3 py-1 text-sm font-bold text-slate-700">SAMPLE DATA</span> */}
      {/* )} */}
      {/* DEPRECATED(closureiq) END */}
      <span
        className={`rounded-full px-3 py-1 text-sm font-bold ${
          dataMode === 'live' ? 'bg-emerald-100 text-emerald-800' : 'bg-violet-100 text-violet-800'
        }`}
      >
        {dataMode.toUpperCase()}
      </span>
      {clockStatus === 'unavailable' ? (
        <span className="rounded-full bg-red-600 px-3 py-1 text-sm font-bold text-white">CLOCK UNAVAILABLE</span>
      ) : (
        <time aria-label="Current time" className="font-mono text-sm text-slate-700">
          {clockStatus === 'loading' ? '--:--:--' : new Date(now).toLocaleTimeString([], { timeZoneName: 'short' })}
        </time>
      )}
      {clockMode === 'simulated' && (
        <span className="rounded-full bg-amber-100 px-3 py-1 text-sm font-bold text-amber-900">
          SIMULATED {speed}x
        </span>
      )}
    </div>
  )
}
