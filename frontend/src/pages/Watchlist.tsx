import { useEffect, useMemo, useState } from 'react'
import { FacilityCard } from '../components/FacilityCard'
import { loadFacilities } from '../fixtures'
import { useEventSource } from '../hooks/useEventSource'
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

type EvaluationCreatedEvent = Pick<Facility['current'], 'evaluation_id' | 'posture' | 'confidence'> & {
  facility_id: string
}

function isEvaluationCreatedEvent(value: unknown): value is EvaluationCreatedEvent {
  if (!value || typeof value !== 'object') {
    return false
  }

  const event = value as Record<string, unknown>
  return (
    typeof event.facility_id === 'string' &&
    typeof event.evaluation_id === 'string' &&
    typeof event.posture === 'string' &&
    event.posture in postureOrder &&
    (event.confidence === 'high' || event.confidence === 'medium' || event.confidence === 'low')
  )
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
  const [now, setNow] = useState(Date.now)
  const { subscribe, onReconnect } = useEventSource()
  const dataMode = facilities[0]?.data_mode ?? 'live'

  useEffect(() => {
    const clockIntervalId = window.setInterval(() => setNow(Date.now()), 1_000)
    return () => window.clearInterval(clockIntervalId)
  }, [])

  useEffect(() => {
    const reloadFacilities = () => setFacilities(loadFacilities())
    const unsubscribeReconnect = onReconnect(reloadFacilities)
    const unsubscribeEvaluation = subscribe('evaluation.created', (event) => {
      try {
        const update: unknown = JSON.parse(event.data)
        if (!isEvaluationCreatedEvent(update)) {
          console.warn('Ignoring malformed evaluation.created event', update)
          return
        }

        setFacilities((currentFacilities) =>
          currentFacilities.map((facility) =>
            facility.facility_id === update.facility_id
              ? {
                  ...facility,
                  current: {
                    ...facility.current,
                    ...update,
                  },
                }
              : facility,
          ),
        )
      } catch (error) {
        console.warn('Unable to parse evaluation.created event', error)
      }
    })

    return () => {
      unsubscribeReconnect()
      unsubscribeEvaluation()
    }
  }, [onReconnect, subscribe])

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
              {new Date(now).toLocaleTimeString()}
            </time>
          </div>
        </header>

        <section aria-label="Facility recommendations" className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {sortedFacilities.map((facility) => (
            <FacilityCard facility={facility} key={facility.facility_id} />
          ))}
        </section>
      </div>
    </main>
  )
}
