import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, evaluateFacility, getFacilities, getFacilityStatus, getRoster } from '../api'
import type { FacilityStatusResult } from '../api'
import { ApprovalDrawer } from '../components/approval/ApprovalDrawer'
import { AffectedEmployees } from '../components/decision/AffectedEmployees'
import { DegradedBanner } from '../components/decision/DegradedBanner'
import { EvidencePanel } from '../components/decision/EvidencePanel'
import { PostureBanner } from '../components/decision/PostureBanner'
import { ReasoningPanel } from '../components/decision/ReasoningPanel'
import { StatusBadges } from '../components/StatusBadges'
import { useEventSource } from '../hooks/useEventSource'
import { useServerClock } from '../hooks/useServerClock'
import type { Approval, Employee, Facility } from '../types'

type PageData = {
  facility: Facility | null
  status: FacilityStatusResult | null
  employees: Employee[]
  fromFixture: boolean
}

async function loadPageData(facilityId: string): Promise<PageData> {
  const [facilitiesResult, statusResult, employees] = await Promise.all([
    getFacilities(),
    getFacilityStatus(facilityId),
    getRoster(facilityId),
  ])
  return {
    facility: facilitiesResult.facilities.find((item) => item.facility_id === facilityId) ?? null,
    status: statusResult.status,
    employees,
    fromFixture: statusResult.fromFixture,
  }
}

type DecisionBarProps = {
  approval: Approval | null
  notificationId: string | null
  onOpen: () => void
}

// Nothing reaches employees until a person decides; this bar is the way in.
function DecisionBar({ approval, notificationId, onOpen }: DecisionBarProps) {
  return (
    <section className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white p-4 shadow-sm">
      <p className="text-sm text-slate-700">
        {approval
          ? `Decision recorded: ${approval.action} by ${approval.actor}.`
          : 'Awaiting a decision. Nothing is sent until an approver acts.'}
      </p>
      <div className="flex flex-wrap gap-2">
        {notificationId && (
          <Link
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-100"
            to={`/notifications/${notificationId}`}
          >
            Delivery tracker
          </Link>
        )}
        <button
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700"
          onClick={onOpen}
          type="button"
        >
          {approval ? 'View decision' : 'Review and decide'}
        </button>
      </div>
    </section>
  )
}

export function FacilityDecision() {
  const { id = '' } = useParams()
  const [data, setData] = useState<PageData | null>(null)
  const [evaluating, setEvaluating] = useState(false)
  const [evaluateError, setEvaluateError] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const closeDrawer = useCallback(() => setDrawerOpen(false), [])
  const { subscribe, onReconnect } = useEventSource()
  const { now, clockMode, speed, dataMode: serverDataMode } = useServerClock()

  const reload = useCallback(() => loadPageData(id).then(setData), [id])

  useEffect(() => {
    loadPageData(id).then(setData)
  }, [id])

  useEffect(() => {
    // Refetch only when an event concerns this facility (or carries no facility_id).
    const forThisFacility = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data) as { facility_id?: string }
        return !payload.facility_id || payload.facility_id === id
      } catch {
        return true
      }
    }
    const refreshEvents = ['evaluation.created', 'approval.recorded', 'source.degraded', 'mode.changed'] as const
    const unsubscribers = [
      onReconnect(() => void reload()),
      ...refreshEvents.map((eventName) =>
        subscribe(eventName, (event) => {
          if (forThisFacility(event)) void reload()
        }),
      ),
    ]
    return () => unsubscribers.forEach((unsubscribe) => unsubscribe())
  }, [id, onReconnect, reload, subscribe])

  const runEvaluation = async () => {
    setEvaluating(true)
    setEvaluateError(null)
    try {
      await evaluateFacility(id)
    } catch (error) {
      // 503 source_unavailable still records a low-confidence evaluation, so reload either way.
      if (!(error instanceof ApiError && error.code === 'source_unavailable')) {
        setEvaluateError(error instanceof Error ? error.message : 'Evaluation failed')
      }
    } finally {
      await reload()
      setEvaluating(false)
    }
  }

  const facility = data?.facility
  const recommendation = data?.status?.evaluation ?? null
  const approval = data?.status?.approval ?? null
  const timeZone = facility?.location.timezone ?? 'America/Chicago'
  const dataMode = serverDataMode ?? recommendation?.data_mode ?? facility?.data_mode ?? 'live'

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-8 text-slate-950 sm:px-10">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <Link className="text-sm font-medium text-blue-700 hover:underline" to="/">
              ← Watchlist
            </Link>
            <h1 className="mt-1 text-3xl font-bold tracking-tight">{facility?.name ?? id}</h1>
          </div>
          <StatusBadges
            clockMode={clockMode}
            dataMode={dataMode}
            fromFixture={data?.fromFixture ?? false}
            now={now}
            speed={speed}
          />
        </header>

        {data === null && <p className="text-slate-600">Loading the latest evaluation…</p>}

        {data !== null && recommendation === null && (
          <section className="rounded-xl bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold">No evaluation yet</h2>
            <p className="mt-1 text-slate-600">
              {data.fromFixture
                ? 'There is no sample recommendation for this facility.'
                : 'The engine has not evaluated this facility yet.'}
            </p>
            {!data.fromFixture && (
              <button
                className="mt-4 rounded-md bg-slate-900 px-4 py-2 font-semibold text-white disabled:opacity-60"
                disabled={evaluating}
                onClick={() => void runEvaluation()}
                type="button"
              >
                {evaluating ? 'Evaluating…' : 'Evaluate now'}
              </button>
            )}
            {evaluateError && <p className="mt-2 text-sm text-red-700">{evaluateError}</p>}
          </section>
        )}

        {data !== null && recommendation !== null && (
          <>
            <DegradedBanner recommendation={recommendation} sources={data.status?.sources ?? []} />
            <PostureBanner now={now} recommendation={recommendation} timeZone={timeZone} />
            <DecisionBar
              approval={approval}
              notificationId={data.status?.notification_id ?? null}
              onOpen={() => setDrawerOpen(true)}
            />
            <ApprovalDrawer
              approval={approval}
              employees={data.employees}
              notificationId={data.status?.notification_id ?? null}
              offline={data.fromFixture}
              onClose={closeDrawer}
              onDecided={() => void reload()}
              open={drawerOpen}
              recommendation={recommendation}
              timeZone={timeZone}
            />
            <div className="grid gap-6 lg:grid-cols-2">
              <EvidencePanel recommendation={recommendation} timeZone={timeZone} />
              <ReasoningPanel recommendation={recommendation} />
            </div>
            <AffectedEmployees employees={data.employees} />
            <p className="text-sm">
              <Link className="font-medium text-blue-700 hover:underline" to={`/records/${recommendation.evaluation_id}`}>
                View the decision record for {recommendation.evaluation_id} →
              </Link>
            </p>
          </>
        )}
      </div>
    </main>
  )
}
