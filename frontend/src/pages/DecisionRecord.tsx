import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getFacilities, getRecord, getRoster, replayEvaluation } from '../api'
import { PackageView } from '../components/approval/PackageView'
import { EvidencePanel } from '../components/decision/EvidencePanel'
import { PostureChip } from '../components/PostureChip'
import { StatusBadges } from '../components/StatusBadges'
import { formatDateTime } from '../format'
import { useServerClock } from '../hooks/useServerClock'
import type { DecisionRecord as RecordData, Employee, Facility, NotificationPackage, ReplayResult } from '../types'

type PageData = { record: RecordData; facility: Facility | null; employees: Employee[] }

async function loadRecord(evaluationId: string): Promise<PageData> {
  const record = await getRecord(evaluationId)
  const facilityId = record.evaluation.facility_id
  const [facilitiesResult, employees] = await Promise.all([getFacilities(), getRoster(facilityId)])
  return {
    record,
    facility: facilitiesResult.facilities.find((item) => item.facility_id === facilityId) ?? null,
    employees,
  }
}

// Saves the whole record as JSON: the artifact a judge can keep (architecture: Export).
function downloadJson(record: RecordData) {
  const blob = new Blob([JSON.stringify(record, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `closureiq-record-${record.evaluation.evaluation_id}.json`
  link.click()
  URL.revokeObjectURL(url)
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl bg-white p-6 shadow-sm">
      <h2 className="text-lg font-bold text-slate-950">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  )
}

// Raw payloads can be large (hourly forecasts), so render them only when opened.
function RawPayload({ payload }: { payload: unknown }) {
  const [open, setOpen] = useState(false)
  return (
    <details onToggle={(event) => setOpen((event.target as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer text-xs font-medium text-blue-700">Raw payload</summary>
      {open && (
        <pre className="mt-2 max-h-80 overflow-auto rounded-md bg-slate-950 p-3 text-xs text-slate-100">
          {JSON.stringify(payload, null, 2)}
        </pre>
      )}
    </details>
  )
}

function ReplayPanel({ evaluationId }: { evaluationId: string }) {
  const [state, setState] = useState<{ running: boolean; result: ReplayResult | null; error: string | null }>({
    running: false,
    result: null,
    error: null,
  })

  const run = async () => {
    setState({ running: true, result: null, error: null })
    try {
      setState({ running: false, result: await replayEvaluation(evaluationId), error: null })
    } catch (error) {
      setState({ running: false, result: null, error: error instanceof Error ? error.message : 'Replay failed' })
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        className="rounded-md bg-slate-900 px-4 py-2 font-semibold text-white disabled:opacity-50"
        disabled={state.running}
        onClick={() => void run()}
        type="button"
      >
        {state.running ? 'Replaying…' : 'Replay'}
      </button>
      {state.result?.identical && (
        <span className="rounded-full bg-emerald-600 px-4 py-1.5 font-bold text-white">
          ✓ Identical: the stored evidence gives the same recommendation
        </span>
      )}
      {state.result && !state.result.identical && (
        <div className="w-full rounded-md border-2 border-red-600 bg-red-50 p-3 text-sm text-red-900">
          <p className="font-bold">Replay differs in {state.result.diff.length} field(s)</p>
          <ul className="mt-1 list-disc pl-5">
            {state.result.diff.slice(0, 10).map((item) => (
              <li key={item.path}>
                <code>{item.path}</code>: stored {JSON.stringify(item.stored)}, replayed {JSON.stringify(item.replayed)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {state.error && <span className="text-sm text-red-700">{state.error}</span>}
    </div>
  )
}

export function DecisionRecord() {
  const { id = '' } = useParams()
  const [data, setData] = useState<PageData | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const { now, clockMode, speed, dataMode } = useServerClock()

  useEffect(() => {
    loadRecord(id)
      .then((result) => {
        setData(result)
        setLoadError(null)
      })
      .catch((error: unknown) => setLoadError(error instanceof Error ? error.message : 'Could not load the record'))
  }, [id])

  const record = data?.record
  const evaluation = record?.evaluation
  const timeZone = data?.facility?.location.timezone ?? 'America/Chicago'
  const notification = record?.notification
  const notificationId = notification?.notification_id ?? notification?.id ?? null

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-8 text-slate-950 sm:px-10">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <Link
              className="text-sm font-medium text-blue-700 hover:underline"
              to={evaluation ? `/facilities/${evaluation.facility_id}` : '/'}
            >
              ← {data?.facility?.name ?? evaluation?.facility_id ?? 'Watchlist'}
            </Link>
            <h1 className="mt-1 text-3xl font-bold tracking-tight">Decision record</h1>
            <p className="mt-1 text-sm text-slate-600">
              {id} · append-only: every row is written once and never changed
            </p>
          </div>
          <StatusBadges
            clockMode={clockMode}
            dataMode={dataMode ?? evaluation?.data_mode ?? 'live'}
            fromFixture={false}
            now={now}
            speed={speed}
          />
        </header>

        {loadError && !data && (
          <p className="rounded-xl bg-white p-6 text-slate-700 shadow-sm">
            Could not load this record: {loadError}. The decision record needs the backend running.
          </p>
        )}
        {!data && !loadError && <p className="text-slate-600">Loading the record…</p>}

        {record && evaluation && (
          <>
            <Section title="Replay">
              <p className="mb-3 text-sm text-slate-700">
                Replay re-runs the engine on the stored raw evidence for {evaluation.evaluation_id} and compares the
                result field by field. It never writes a new evaluation.
              </p>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <ReplayPanel evaluationId={evaluation.evaluation_id} />
                <button
                  className="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-100"
                  onClick={() => downloadJson(record)}
                  type="button"
                >
                  Download JSON
                </button>
              </div>
            </Section>

            <Section title="Evaluation chain">
              <ol className="flex flex-wrap items-center gap-2 text-sm">
                {record.chain.map((evaluationId, index) => (
                  <li className="flex items-center gap-2" key={evaluationId}>
                    {index > 0 && <span className="text-slate-400">→</span>}
                    {evaluationId === evaluation.evaluation_id ? (
                      <span className="rounded-md bg-slate-900 px-2 py-1 font-semibold text-white">{evaluationId}</span>
                    ) : (
                      <Link className="rounded-md bg-slate-100 px-2 py-1 text-slate-800 hover:bg-slate-200" to={`/records/${evaluationId}`}>
                        {evaluationId}
                      </Link>
                    )}
                  </li>
                ))}
              </ol>
            </Section>

            <Section title="Recommendation">
              <div className="flex flex-wrap items-center gap-3 text-sm text-slate-700">
                <PostureChip posture={evaluation.posture} />
                {evaluation.held_by_hysteresis && (
                  <span>
                    held by hysteresis (engine computed <PostureChip posture={evaluation.raw_posture} />)
                  </span>
                )}
                <span>confidence {evaluation.confidence.level}</span>
                <span>· {formatDateTime(evaluation.evaluated_at, timeZone)}</span>
                <span>· {evaluation.policy_version}</span>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-slate-800">{evaluation.rationale}</p>
            </Section>

            <EvidencePanel recommendation={evaluation} timeZone={timeZone} />

            <Section title={`Evidence snapshots (${record.evidence.length})`}>
              <ul className="space-y-3">
                {record.evidence.map((snapshot) => (
                  <li className="rounded-lg border border-slate-200 p-3" key={snapshot.snapshot_id}>
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="font-semibold text-slate-950">{snapshot.source}</span>
                      <span className="text-slate-500">{snapshot.snapshot_id}</span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                          snapshot.ok ? 'bg-emerald-100 text-emerald-800' : 'bg-red-600 text-white'
                        }`}
                      >
                        {snapshot.ok ? `HTTP ${snapshot.http_status ?? 'ok'}` : `Failed${snapshot.http_status ? ` (HTTP ${snapshot.http_status})` : ''}`}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      Fetched {formatDateTime(snapshot.fetched_at_wall, timeZone)} (wall)
                      {snapshot.fetched_at_sim !== snapshot.fetched_at_wall && <> · {formatDateTime(snapshot.fetched_at_sim, timeZone)} (simulated)</>}
                    </p>
                    <p className="mt-1 break-all text-xs text-slate-500">{snapshot.url}</p>
                    {snapshot.error && <p className="mt-1 text-xs text-red-700">{snapshot.error}</p>}
                    <div className="mt-2">
                      <RawPayload payload={snapshot.raw_payload} />
                    </div>
                  </li>
                ))}
              </ul>
            </Section>

            <Section title="Approval">
              {record.approval ? (
                <div className="space-y-1 text-sm text-slate-700">
                  <p>
                    <strong className="capitalize">{record.approval.action}</strong> by {record.approval.actor} at{' '}
                    {formatDateTime(record.approval.acted_at_wall, timeZone)}
                    {record.approval.acted_at_sim && record.approval.acted_at_sim !== record.approval.acted_at_wall && (
                      <> (simulated {formatDateTime(record.approval.acted_at_sim, timeZone)})</>
                    )}
                  </p>
                  <p className="flex flex-wrap items-center gap-2">
                    Final posture <PostureChip posture={record.approval.final_posture} />
                    {record.approval.final_posture !== evaluation.posture && (
                      <>
                        · engine recommended <PostureChip posture={evaluation.posture} />
                      </>
                    )}
                  </p>
                  {record.approval.reason && <p>Reason: {record.approval.reason}</p>}
                </div>
              ) : (
                <p className="text-sm text-slate-600">No decision has been recorded for this evaluation.</p>
              )}
            </Section>

            {notification?.package && (
              <Section title={`Notification package${notificationId ? ` ${notificationId}` : ''}`}>
                <details>
                  <summary className="cursor-pointer text-sm font-medium text-blue-700">
                    Show recipients, messages and routing
                  </summary>
                  <div className="mt-3">
                    <PackageView employees={data.employees} notification={notification as NotificationPackage} />
                  </div>
                </details>
                {notificationId && (
                  <Link className="mt-3 inline-block text-sm font-medium text-blue-700 hover:underline" to={`/notifications/${notificationId}`}>
                    Open delivery tracker →
                  </Link>
                )}
              </Section>
            )}

            {record.deliveries.length > 0 && (
              <Section title={`Deliveries (${record.deliveries.length})`}>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-xs uppercase text-slate-500">
                      <tr>
                        <th className="py-1 pr-3">Delivery</th>
                        <th className="py-1 pr-3">Recipient</th>
                        <th className="py-1 pr-3">Channel</th>
                        <th className="py-1">Status history</th>
                      </tr>
                    </thead>
                    <tbody>
                      {record.deliveries.map((delivery) => (
                        <tr className="border-t border-slate-100 align-top" key={delivery.delivery_id}>
                          <td className="py-1.5 pr-3 text-slate-500">{delivery.delivery_id}</td>
                          <td className="py-1.5 pr-3">
                            {data.employees.find((employee) => employee.employee_id === delivery.recipient_id)?.name ??
                              delivery.recipient_id}
                          </td>
                          <td className="py-1.5 pr-3">
                            {delivery.channel} {delivery.real ? '(real)' : '(simulated)'}
                          </td>
                          <td className="py-1.5 text-slate-700">
                            {delivery.status_history
                              .map((item) => `${item.status} ${formatDateTime(item.at_wall, timeZone)}`)
                              .join(' → ')}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Section>
            )}

            {(record.timers.length > 0 || record.audit_log.length > 0) && (
              <Section title="Timers and audit log">
                <pre className="max-h-80 overflow-auto rounded-md bg-slate-100 p-3 text-xs text-slate-800">
                  {JSON.stringify({ timers: record.timers, audit_log: record.audit_log }, null, 2)}
                </pre>
              </Section>
            )}
          </>
        )}
      </div>
    </main>
  )
}
