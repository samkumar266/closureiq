import { useCallback, useEffect, useMemo, useState } from 'react'
import { getFacilities } from '../api'
import { FacilityCard } from '../components/FacilityCard'
import { loadFacilities } from '../fixtures'
import { useEventSource } from '../hooks/useEventSource'
import { useServerClock } from '../hooks/useServerClock'
import type { AlertTier, Facility } from '../types'

const postureOrder: Record<Facility['current']['posture'], number> = {
  closure: 0,
  early_dismissal: 1,
  delayed_arrival: 2,
  unscheduled_leave_or_telework: 3,
  normal_operations: 4,
}
const alertTierOrder: Record<AlertTier, number> = {
  warning: 0,
  watch: 1,
  advisory: 2,
  none: 3,
}

function sortFacilities(facilities: Facility[]) {
  return [...facilities].sort(
    (left, right) =>
      alertTierOrder[left.highest_alert_tier] - alertTierOrder[right.highest_alert_tier] ||
      postureOrder[left.current.posture] - postureOrder[right.current.posture],
  )
}

export function Watchlist() {
  const [facilities, setFacilities] = useState(loadFacilities)
  const [fromFixture, setFromFixture] = useState(true)
  const { subscribe, onReconnect } = useEventSource()
  const { now, clockMode, speed, dataMode: serverDataMode } = useServerClock()
  const dataMode = serverDataMode ?? facilities[0]?.data_mode ?? 'live'

  const reloadFacilities = useCallback(
    () =>
      getFacilities().then((result) => {
        setFacilities(result.facilities)
        setFromFixture(result.fromFixture)
      }),
    [],
  )

  useEffect(() => {
    getFacilities().then((result) => {
      setFacilities(result.facilities)
      setFromFixture(result.fromFixture)
    })
  }, [])

  useEffect(() => {
    // These events change card fields the event payload does not carry
    // (headline, deadline, alert tier, approval status, source health), so refetch the list.
    const refreshEvents = ['evaluation.created', 'approval.recorded', 'source.degraded', 'mode.changed'] as const
    const unsubscribers = [
      onReconnect(() => void reloadFacilities()),
      ...refreshEvents.map((eventName) => subscribe(eventName, () => void reloadFacilities())),
    ]

    return () => unsubscribers.forEach((unsubscribe) => unsubscribe())
  }, [onReconnect, reloadFacilities, subscribe])

  const sortedFacilities = useMemo(() => sortFacilities(facilities), [facilities])

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-8 text-slate-950 sm:px-10">
      <div className="mx-auto max-w-6xl">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Watchlist</h1>
            <p className="mt-1 text-slate-600">Current facility operating recommendations</p>
          </div>
          <div className="flex items-center gap-3">
            {fromFixture && (
              <span className="rounded-full bg-slate-200 px-3 py-1 text-sm font-bold text-slate-700">
                SAMPLE DATA
              </span>
            )}
            <span
              className={`rounded-full px-3 py-1 text-sm font-bold ${
                dataMode === 'live'
                  ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-violet-100 text-violet-800'
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
        </header>

        <section aria-label="Facility recommendations" className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {sortedFacilities.map((facility) => (
            <FacilityCard facility={facility} key={facility.facility_id} now={now} />
          ))}
        </section>
      </div>
    </main>
  )
}
