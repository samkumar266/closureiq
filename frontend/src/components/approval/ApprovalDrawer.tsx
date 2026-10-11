import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ApiError,
  approveEvaluation,
  getPackagePreview,
  overrideEvaluation,
  rejectEvaluation,
} from '../../api'
import { formatDateTime } from '../../format'
import { postureTheme, type Posture } from '../../theme'
import type { Approval, Employee, NotificationPackage, Recommendation } from '../../types'
import { PostureChip } from '../PostureChip'
import { PackageView } from './PackageView'

type Action = 'approve' | 'reject' | 'override'

type ApprovalDrawerProps = {
  open: boolean
  onClose: () => void
  recommendation: Recommendation
  employees: Employee[]
  approval: Approval | null
  notificationId: string | null
  timeZone: string
  offline: boolean
  // Called after any decision or a stale/already-decided answer, so the page reloads its status.
  onDecided: () => void
}

const ACTOR_KEY = 'closureiq.actor'
const postures = Object.keys(postureTheme) as Posture[]
const actionLabels: Record<Action, string> = { approve: 'Approve', reject: 'Reject', override: 'Override' }

function readSavedActor() {
  try {
    return window.localStorage.getItem(ACTOR_KEY) ?? ''
  } catch {
    return ''
  }
}

function saveActor(actor: string) {
  try {
    window.localStorage.setItem(ACTOR_KEY, actor)
  } catch {
    // Storage can be blocked; the name is still sent with this decision.
  }
}

function DecisionSummary({ approval, notificationId, timeZone }: { approval: Approval; notificationId: string | null; timeZone: string }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-700">
        <strong className="capitalize">{approval.action === 'approve' ? 'Approved' : approval.action === 'reject' ? 'Rejected' : 'Overridden'}</strong>{' '}
        by {approval.actor} at {formatDateTime(approval.acted_at_wall, timeZone)}.
      </p>
      <p className="flex flex-wrap items-center gap-2 text-sm text-slate-700">
        Final posture: <PostureChip posture={approval.final_posture} />
      </p>
      {approval.reason && <p className="text-sm text-slate-700">Reason: {approval.reason}</p>}
      {notificationId ? (
        <Link
          className="inline-block rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700"
          to={`/notifications/${notificationId}`}
        >
          Open delivery tracker →
        </Link>
      ) : (
        <p className="text-sm text-slate-600">No notification was sent for this decision.</p>
      )}
    </div>
  )
}

export function ApprovalDrawer(props: ApprovalDrawerProps) {
  const { open, onClose, recommendation, employees, approval, notificationId, timeZone, offline, onDecided } = props
  const [actor, setActor] = useState(readSavedActor)
  const [action, setAction] = useState<Action>('approve')
  const [overridePosture, setOverridePosture] = useState<Posture>(
    postures.find((posture) => posture !== recommendation.posture) ?? 'normal_operations',
  )
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [staleLatestId, setStaleLatestId] = useState<string | null>(null)
  // Preview is keyed by evaluation and posture so a stale response is never shown for another choice.
  const [preview, setPreview] = useState<{ key: string; data: NotificationPackage | null; error: string | null } | null>(null)

  const evaluationId = recommendation.evaluation_id
  const previewPosture = action === 'override' ? overridePosture : undefined
  const previewKey = `${evaluationId}:${previewPosture ?? 'engine'}`
  const showPreview = open && !approval && !offline && action !== 'reject'

  useEffect(() => {
    if (!showPreview) return
    let cancelled = false
    getPackagePreview(evaluationId, previewPosture)
      .then((data) => !cancelled && setPreview({ key: previewKey, data, error: null }))
      .catch((caught: unknown) => {
        if (!cancelled) {
          setPreview({ key: previewKey, data: null, error: caught instanceof Error ? caught.message : 'Preview failed' })
        }
      })
    return () => {
      cancelled = true
    }
  }, [evaluationId, previewKey, previewPosture, showPreview])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open) return null

  const needsReason = action !== 'approve'
  const canSubmit = !submitting && actor.trim() !== '' && (!needsReason || reason.trim() !== '')
  const currentPreview = preview?.key === previewKey ? preview : null

  const submit = async () => {
    setSubmitting(true)
    setError(null)
    setStaleLatestId(null)
    saveActor(actor.trim())
    try {
      if (action === 'approve') await approveEvaluation(evaluationId, actor.trim())
      if (action === 'reject') await rejectEvaluation(evaluationId, actor.trim(), reason.trim())
      if (action === 'override') await overrideEvaluation(evaluationId, actor.trim(), overridePosture, reason.trim())
      onDecided()
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === 'already_decided') {
        // Idempotent: a decision already exists, so just show it.
        onDecided()
      } else if (caught instanceof ApiError && caught.code === 'stale_evaluation') {
        setStaleLatestId(String(caught.detail.latest_id ?? 'a newer evaluation'))
      } else {
        setError(caught instanceof Error ? caught.message : 'The decision could not be recorded')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-label="Approval">
      <button aria-label="Close approval panel" className="absolute inset-0 bg-slate-950/40" onClick={onClose} type="button" />
      <aside className="relative flex h-full w-full max-w-2xl flex-col overflow-y-auto bg-white shadow-xl">
        <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-slate-200 bg-white p-5">
          <div>
            <h2 className="text-xl font-bold text-slate-950">Decide on {evaluationId}</h2>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-600">
              The engine recommends <PostureChip posture={recommendation.posture} />
            </p>
          </div>
          <button className="rounded-md px-2 py-1 text-slate-500 hover:bg-slate-100" onClick={onClose} type="button">
            Close ✕
          </button>
        </header>

        <div className="space-y-5 p-5">
          {approval ? (
            <DecisionSummary approval={approval} notificationId={notificationId} timeZone={timeZone} />
          ) : offline ? (
            <p className="rounded-md bg-slate-100 p-3 text-sm text-slate-700">
              The backend is not connected, so decisions cannot be recorded. Start the API to approve.
            </p>
          ) : (
            <>
              <label className="block text-sm font-medium text-slate-900">
                Your name (recorded as the approver)
                <input
                  className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2"
                  onChange={(event) => setActor(event.target.value)}
                  placeholder="For example: Dana (Safety Officer)"
                  value={actor}
                />
              </label>

              <div className="flex gap-2" role="tablist" aria-label="Decision">
                {(Object.keys(actionLabels) as Action[]).map((item) => (
                  <button
                    aria-selected={action === item}
                    className={`rounded-md px-4 py-2 text-sm font-semibold ${
                      action === item ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-800 hover:bg-slate-200'
                    }`}
                    key={item}
                    onClick={() => setAction(item)}
                    role="tab"
                    type="button"
                  >
                    {actionLabels[item]}
                  </button>
                ))}
              </div>

              {action === 'override' && (
                <label className="block text-sm font-medium text-slate-900">
                  Posture to send instead
                  <select
                    className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2"
                    onChange={(event) => setOverridePosture(event.target.value as Posture)}
                    value={overridePosture}
                  >
                    {postures
                      .filter((posture) => posture !== recommendation.posture)
                      .map((posture) => (
                        <option key={posture} value={posture}>
                          {postureTheme[posture].label}
                        </option>
                      ))}
                  </select>
                  <span className="mt-1 block text-xs font-normal text-slate-500">
                    The engine's recommendation stays in the record next to your override.
                  </span>
                </label>
              )}

              {needsReason && (
                <label className="block text-sm font-medium text-slate-900">
                  Reason (required)
                  <textarea
                    className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2"
                    onChange={(event) => setReason(event.target.value)}
                    rows={3}
                    value={reason}
                  />
                </label>
              )}

              {staleLatestId && (
                <div className="rounded-md border-2 border-amber-500 bg-amber-50 p-3 text-sm text-amber-900" role="alert">
                  <p className="font-semibold">A newer evaluation ({staleLatestId}) has replaced this one.</p>
                  <p className="mt-1">Nothing was recorded. Review the latest recommendation before deciding.</p>
                  <button className="mt-2 rounded-md bg-amber-600 px-3 py-1.5 font-semibold text-white" onClick={onDecided} type="button">
                    Load the latest evaluation
                  </button>
                </div>
              )}
              {error && (
                <p className="rounded-md bg-red-50 p-3 text-sm text-red-800" role="alert">
                  {error}
                </p>
              )}

              <button
                className="w-full rounded-md bg-slate-900 px-4 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!canSubmit}
                onClick={() => void submit()}
                type="button"
              >
                {submitting
                  ? 'Recording…'
                  : action === 'approve'
                    ? 'Approve and send notifications'
                    : action === 'reject'
                      ? 'Reject (nothing is sent)'
                      : `Override to ${postureTheme[overridePosture].label.toLowerCase()} and send`}
              </button>

              {action === 'reject' ? (
                <p className="text-sm text-slate-600">
                  Rejecting sends nothing. The evaluation stays in the record and the engine keeps watching.
                </p>
              ) : (
                <section aria-label="Notification preview" className="border-t border-slate-200 pt-5">
                  <h3 className="text-lg font-bold text-slate-950">
                    Notification preview{action === 'override' && ` for ${postureTheme[overridePosture].label.toLowerCase()}`}
                  </h3>
                  {!currentPreview ? (
                    <p className="mt-2 text-sm text-slate-600">Building the package…</p>
                  ) : currentPreview.error ? (
                    <p className="mt-2 text-sm text-red-700">Preview unavailable: {currentPreview.error}</p>
                  ) : (
                    currentPreview.data && (
                      <div className="mt-3">
                        <PackageView employees={employees} notification={currentPreview.data} />
                      </div>
                    )
                  )}
                </section>
              )}
            </>
          )}
        </div>
      </aside>
    </div>
  )
}
