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
  // The facility's IANA timezone, so the header clock matches every other time on the page.
  // Undefined until the facility profile has loaded; the clock waits rather than guessing a timezone.
  timeZone: string | undefined
}

// Data mode and clock badges. Shown on every screen so replay data or a missing server clock is never hidden.
export function StatusBadges({ dataMode, now, clockMode, clockStatus, speed, timeZone }: StatusBadgesProps) {
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
          {/* DEPRECATED(closureiq): browser timezone; the clock now shows the facility's local time. */}
          {/* {clockStatus === 'loading' ? '--:--:--' : new Date(now).toLocaleTimeString([], { timeZoneName: 'short' })} */}
          {clockStatus === 'loading' || !timeZone
            ? '--:--:--'
            : new Date(now).toLocaleTimeString([], { timeZone, timeZoneName: 'short' })}
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
