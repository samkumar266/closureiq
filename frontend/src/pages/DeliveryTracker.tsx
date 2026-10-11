import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
// DEPRECATED(closureiq): facility name and timezone now come from the profile endpoint, not the facility list.
// import { acknowledgeDelivery, getEvaluation, getFacilities, getNotification, getRoster, setClock } from '../api'
import { acknowledgeDelivery, getEvaluation, getFacilityProfile, getNotification, getRoster, setClock } from '../api'
import { StatusBadges } from '../components/StatusBadges'
import { formatDateTime } from '../format'
import { groupLabel } from '../groups'
import { useEventSource } from '../hooks/useEventSource'
import { requestClockRefresh, useServerClock } from '../hooks/useServerClock'
import { postureTheme } from '../theme'
// DEPRECATED(closureiq): Facility list item type retired with the Watchlist.
// import type { Delivery, DeliveryStatus, Employee, Facility, NotificationPackage, Recommendation } from '../types'
import type { Delivery, DeliveryStatus, Employee, FacilityProfile, NotificationPackage, Recommendation } from '../types'

// DEPRECATED(closureiq) START: loader that swallowed a failed evaluation lookup and searched the facility list.
// type TrackerData = {
//   notification: NotificationPackage
//   evaluation: Recommendation | null
//   facility: Facility | null
//   employees: Employee[]
// }
//
// async function loadTracker(notificationId: string): Promise<TrackerData> {
//   const notification = await getNotification(notificationId)
//   const evaluation = await getEvaluation(notification.evaluation_id).catch(() => null)
//   const facilityId = evaluation?.facility_id
//   const [facilitiesResult, employees] = await Promise.all([
//     getFacilities(),
//     facilityId ? getRoster(facilityId) : Promise.resolve([]),
//   ])
//   return {
//     notification,
//     evaluation,
//     facility: facilitiesResult.facilities.find((item) => item.facility_id === facilityId) ?? null,
//     employees,
//   }
// }
// DEPRECATED(closureiq) END

type TrackerData = {
  notification: NotificationPackage
  evaluation: Recommendation
  facility: FacilityProfile
  employees: Employee[]
}

// Any failed call throws, so the page shows the error instead of a partial tracker.
async function loadTracker(notificationId: string): Promise<TrackerData> {
  const notification = await getNotification(notificationId)
  const evaluation = await getEvaluation(notification.evaluation_id)
  const [facility, employees] = await Promise.all([
    getFacilityProfile(evaluation.facility_id),
    getRoster(evaluation.facility_id),
  ])
  return { notification, evaluation, facility, employees }
}

const statusStyles: Record<DeliveryStatus, string> = {
  queued: 'bg-slate-100 text-slate-700',
  sent: 'bg-blue-100 text-blue-800',
  delivered: 'bg-indigo-100 text-indigo-800',
  simulated: 'bg-violet-100 text-violet-800',
  failed: 'bg-red-600 text-white',
  acknowledged: 'bg-emerald-100 text-emerald-800',
}

// Acknowledgment means received. The UI never says understood (architecture: delivery simulator).
const statusLabels: Record<DeliveryStatus, string> = {
  queued: 'Queued',
  sent: 'Sent',
  delivered: 'Delivered',
  simulated: 'Sent (simulated)',
  failed: 'Failed',
  acknowledged: 'Acknowledged receipt',
}

function StatusChip({ status }: { status: DeliveryStatus }) {
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${statusStyles[status] ?? statusStyles.queued}`}>
      {statusLabels[status] ?? status}
    </span>
  )
}

export function DeliveryTracker() {
  const { id = '' } = useParams()
  const [data, setData] = useState<TrackerData | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busy, setBusy] = useState<Set<string>>(new Set())
  const { subscribe, onReconnect } = useEventSource()
  const { now, clockMode, clockStatus, speed, dataMode } = useServerClock()

  const reload = useCallback(
    () =>
      loadTracker(id)
        .then((result) => {
          setData(result)
          setLoadError(null)
        })
        .catch((error: unknown) => setLoadError(error instanceof Error ? error.message : 'Could not load deliveries')),
    [id],
  )

  useEffect(() => {
    loadTracker(id)
      .then(setData)
      .catch((error: unknown) => setLoadError(error instanceof Error ? error.message : 'Could not load deliveries'))
  }, [id])

  useEffect(() => {
    const forThisNotification = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data) as { notification_id?: string }
        return !payload.notification_id || payload.notification_id === id
      } catch {
        return true
      }
    }
    const unsubscribers = [
      onReconnect(() => void reload()),
      ...(['delivery.updated', 'escalation.fired'] as const).map((eventName) =>
        subscribe(eventName, (event) => {
          if (forThisNotification(event)) void reload()
        }),
      ),
    ]
    return () => unsubscribers.forEach((unsubscribe) => unsubscribe())
  }, [id, onReconnect, reload, subscribe])

  const acknowledge = async (deliveryIds: string[]) => {
    setBusy((current) => new Set([...current, ...deliveryIds]))
    await Promise.allSettled(deliveryIds.map((deliveryId) => acknowledgeDelivery(deliveryId)))
    setBusy((current) => new Set([...current].filter((item) => !deliveryIds.includes(item))))
    await reload()
  }

  const timeZone = data?.facility?.location.timezone ?? 'America/Chicago'
  const deliveries = data?.notification.deliveries ?? []
  const nameOf = (employeeId: string) =>
    data?.employees.find((employee) => employee.employee_id === employeeId)?.name ?? employeeId
  const groupOf = (employeeId: string) =>
    data?.notification.package.recipients.find((recipient) => recipient.employee_id === employeeId)?.group ?? ''

  // A person counts as acknowledged once any of their channels is acknowledged.
  const recipientIds = [...new Set(deliveries.map((delivery) => delivery.recipient_id))]
  const acknowledgedIds = new Set(
    deliveries.filter((delivery) => delivery.status === 'acknowledged').map((delivery) => delivery.recipient_id),
  )
  const waiting = recipientIds.filter((recipientId) => !acknowledgedIds.has(recipientId))
  const failedCount = deliveries.filter((delivery) => delivery.status === 'failed').length
  const firstUnacknowledgedDelivery = (recipientId: string) =>
    deliveries.find((delivery) => delivery.recipient_id === recipientId && delivery.status !== 'acknowledged')

  // +30 min: move the simulated clock ahead (POST /api/clock fires due timers in the
  // same request), then refresh so missed acknowledgments and escalations show.
  const [jumping, setJumping] = useState(false)
  const [jumpError, setJumpError] = useState<string | null>(null)
  const jumpAhead = async () => {
    setJumping(true)
    setJumpError(null)
    try {
      await setClock({
        mode: 'simulated',
        speed: clockMode === 'simulated' ? speed : 1,
        set_to: new Date(now + 30 * 60_000).toISOString(),
      })
    } catch (error) {
      setJumpError(error instanceof Error ? error.message : 'Clock change failed')
    } finally {
      requestClockRefresh()
      await reload()
      setJumping(false)
    }
  }

  // Simulate responses: acknowledge most people, leaving a few so escalation has something to show.
  const simulateResponses = () => {
    const toAcknowledge = waiting.slice(0, Math.max(0, waiting.length - Math.ceil(waiting.length * 0.2)))
    const deliveryIds = toAcknowledge
      .map((recipientId) => firstUnacknowledgedDelivery(recipientId)?.delivery_id)
      .filter((deliveryId): deliveryId is string => Boolean(deliveryId))
    void acknowledge(deliveryIds)
  }

  const byRecipient = recipientIds.map((recipientId) => ({
    recipientId,
    rows: deliveries.filter((delivery) => delivery.recipient_id === recipientId),
  }))

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-8 text-slate-950 sm:px-10">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div>
            {data?.evaluation ? (
              <Link className="text-sm font-medium text-blue-700 hover:underline" to={`/facilities/${data.evaluation.facility_id}`}>
                ← {data.facility?.name ?? data.evaluation.facility_id}
              </Link>
            ) : (
              // DEPRECATED(closureiq): "← Watchlist" label; "/" now opens the demo facility.
              <Link className="text-sm font-medium text-blue-700 hover:underline" to="/">
                ← Facility
              </Link>
            )}
            <h1 className="mt-1 text-3xl font-bold tracking-tight">Delivery tracker</h1>
            <p className="mt-1 text-sm text-slate-600">
              Notification {id}
              {data?.notification.approval_id && <> · approval {data.notification.approval_id}</>}
              {data?.notification.standing_policy && <> · sent under standing policy ({data.notification.standing_policy})</>}
            </p>
          </div>
          <StatusBadges
            clockMode={clockMode}
            dataMode={dataMode ?? data?.evaluation?.data_mode ?? 'live'}
            clockStatus={clockStatus}
            // DEPRECATED(closureiq): SAMPLE DATA badge retired with the fixture fallback.
            // fromFixture={false}
            now={now}
            speed={speed}
          />
        </header>

        {loadError && !data && (
          <p className="rounded-xl bg-white p-6 text-slate-700 shadow-sm">
            Could not load this notification: {loadError}. The delivery tracker needs the backend running.
          </p>
        )}
        {!data && !loadError && <p className="text-slate-600">Loading deliveries…</p>}

        {data && (
          <>
            <section className="grid gap-4 sm:grid-cols-4">
              <div className="rounded-xl bg-white p-4 shadow-sm">
                <p className="text-sm text-slate-500">People notified</p>
                <p className="text-3xl font-bold">{recipientIds.length}</p>
              </div>
              <div className="rounded-xl bg-white p-4 shadow-sm">
                <p className="text-sm text-slate-500">Acknowledged receipt</p>
                <p className="text-3xl font-bold text-emerald-700">{acknowledgedIds.size}</p>
              </div>
              <div className="rounded-xl bg-white p-4 shadow-sm">
                <p className="text-sm text-slate-500">Not yet acknowledged</p>
                <p className="text-3xl font-bold text-amber-700">{waiting.length}</p>
              </div>
              <div className="rounded-xl bg-white p-4 shadow-sm">
                <p className="text-sm text-slate-500">Failed messages</p>
                <p className="text-3xl font-bold text-red-700">{failedCount}</p>
              </div>
            </section>

            {data.evaluation && (
              <p className="text-sm text-slate-700">
                Posture sent:{' '}
                <strong>
                  {postureTheme[data.evaluation.posture]?.label ?? data.evaluation.posture}
                </strong>
                {data.notification.ack_deadline && <> · acknowledge by {formatDateTime(data.notification.ack_deadline, timeZone)}</>}
                {data.notification.next_update && <> · next update {formatDateTime(data.notification.next_update, timeZone)}</>}
              </p>
            )}

            <section aria-label="Escalation" className="rounded-xl bg-white p-6 shadow-sm">
              <h2 className="text-lg font-bold">Escalation</h2>
              {data.notification.escalation.length === 0 ? (
                <p className="mt-2 text-sm text-slate-600">
                  No escalation steps scheduled yet. When timers fire, people who have not acknowledged go to the manager
                  and their supervisors.
                </p>
              ) : (
                <ol className="mt-3 space-y-3 border-l-2 border-slate-200 pl-4">
                  {data.notification.escalation.map((step) => {
                    const due = new Date(step.due_sim).getTime()
                    return (
                      <li key={step.step}>
                        <p className="font-semibold text-slate-900">{step.label}</p>
                        <p className="text-sm text-slate-600">
                          {step.fired_at_sim
                            ? `Fired at ${formatDateTime(step.fired_at_sim, timeZone)}`
                            : due <= now
                              ? `Due now (${formatDateTime(step.due_sim, timeZone)})`
                              : `Due ${formatDateTime(step.due_sim, timeZone)}`}
                        </p>
                      </li>
                    )
                  })}
                </ol>
              )}
              {waiting.length > 0 && (
                <p className="mt-3 text-sm text-slate-700">
                  Waiting on: {waiting.slice(0, 8).map(nameOf).join(', ')}
                  {waiting.length > 8 && ` and ${waiting.length - 8} more`}
                </p>
              )}
            </section>

            <section aria-label="Deliveries" className="rounded-xl bg-white p-6 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-lg font-bold">Deliveries</h2>
                <button
                  className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                  disabled={waiting.length === 0 || busy.size > 0}
                  onClick={simulateResponses}
                  type="button"
                >
                  Simulate responses
                </button>
                <button
                  className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-900 disabled:opacity-50"
                  disabled={jumping}
                  onClick={() => void jumpAhead()}
                  title="Move the simulated clock ahead 30 minutes"
                  type="button"
                >
                  {jumping ? 'Jumping…' : '+30 min'}
                </button>
                {jumpError && <span className="text-sm text-red-700">{jumpError}</span>}
              </div>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-xs uppercase text-slate-500">
                    <tr>
                      <th className="py-2 pr-3">Recipient</th>
                      <th className="py-2 pr-3">Channel</th>
                      <th className="py-2 pr-3">Status</th>
                      <th className="py-2 pr-3">Updated</th>
                      <th className="py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {byRecipient.map(({ recipientId, rows }) =>
                      rows.map((delivery: Delivery, index) => (
                        <tr className="border-t border-slate-100 align-top" key={delivery.delivery_id}>
                          <td className="py-2 pr-3">
                            {index === 0 && (
                              <>
                                <span className="font-medium text-slate-900">{nameOf(recipientId)}</span>
                                <span className="block text-xs text-slate-500">{groupLabel(groupOf(recipientId))}</span>
                              </>
                            )}
                          </td>
                          <td className="py-2 pr-3">
                            {delivery.channel}{' '}
                            <span
                              className={`ml-1 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                                delivery.real ? 'bg-emerald-600 text-white' : 'bg-slate-200 text-slate-700'
                              }`}
                            >
                              {delivery.real ? 'Real' : 'Simulated'}
                            </span>
                          </td>
                          <td className="py-2 pr-3">
                            <StatusChip status={delivery.status} />
                          </td>
                          <td className="py-2 pr-3 text-slate-600">{formatDateTime(delivery.status_at_wall, timeZone)}</td>
                          <td className="py-2 text-right">
                            {delivery.status !== 'acknowledged' && (
                              <button
                                className="rounded-md border border-slate-300 px-3 py-1 text-xs font-semibold text-slate-800 hover:bg-slate-100 disabled:opacity-50"
                                disabled={busy.has(delivery.delivery_id)}
                                onClick={() => void acknowledge([delivery.delivery_id])}
                                type="button"
                              >
                                Simulate acknowledge
                              </button>
                            )}
                          </td>
                        </tr>
                      )),
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            {data.evaluation && (
              <p className="text-sm">
                <Link className="font-medium text-blue-700 hover:underline" to={`/records/${data.evaluation.evaluation_id}`}>
                  View the decision record for {data.evaluation.evaluation_id} →
                </Link>
              </p>
            )}
          </>
        )}
      </div>
    </main>
  )
}
