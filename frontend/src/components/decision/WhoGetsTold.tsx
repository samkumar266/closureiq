import { useEffect, useState } from 'react'
import { getNotification, getPackagePreview } from '../../api'
import { employeeGroups, groupLabel } from '../../groups'
import { postureTheme } from '../../theme'
import type { Employee, NotificationPackage, PackageRecipient, Recommendation } from '../../types'

type WhoGetsToldProps = {
  recommendation: Recommendation
  employees: Employee[]
  // Set once a decision was sent; then the section shows the real package instead of the preview.
  notificationId: string | null
  timeZone: string
  commuteBufferMin: number
  now: number
}

type Timing = 'on_site' | 'arriving' | 'later' | 'not_working'

// Brief: "before they've already left the house". Ordered by how soon each person needs to know.
const timingSections: { id: Timing; title: string; note: string }[] = [
  { id: 'on_site', title: 'On site now', note: 'Shift in progress; tell them first' },
  { id: 'arriving', title: 'Starting later today', note: 'Must be told before they leave home' },
  { id: 'later', title: 'Shift already over today', note: 'Next shift is tomorrow' },
  { id: 'not_working', title: 'Not on site today', note: 'Teleworking, on leave, off or detailed elsewhere' },
]

const NOT_ON_SITE = new Set(['teleworking', 'telework', 'on_leave', 'leave', 'day_off', 'off', 'on_detail'])

const toMinutes = (hhmm: string) => {
  const [hours, minutes] = hhmm.split(':').map(Number)
  return hours * 60 + minutes
}

const clock = (minutes: number) => {
  const wrapped = ((minutes % 1440) + 1440) % 1440
  const hours = Math.floor(wrapped / 60)
  return `${hours % 12 || 12}:${String(wrapped % 60).padStart(2, '0')} ${hours < 12 ? 'AM' : 'PM'}`
}

// Minutes since midnight at the facility, on the server's (possibly simulated) clock.
function facilityMinutes(now: number, timeZone: string) {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
    .formatToParts(now)
  const value = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? 0)
  return value('hour') * 60 + value('minute')
}

function timingOf(employee: Employee, nowMinutes: number): Timing {
  if (NOT_ON_SITE.has(employee.work_status_today)) return 'not_working'
  const start = toMinutes(employee.shift_start)
  const end = toMinutes(employee.shift_end)
  const overnight = end <= start
  const inProgress = overnight ? nowMinutes >= start || nowMinutes < end : nowMinutes >= start && nowMinutes < end
  if (inProgress) return 'on_site'
  return nowMinutes < start ? 'arriving' : 'later'
}

// The template's "What to do:" line is the one sentence a person most needs.
const whatToDo = (text: string) => text.split('\n').find((line) => line.startsWith('What to do:'))?.replace('What to do: ', '')

export function WhoGetsTold(props: WhoGetsToldProps) {
  const { recommendation, employees, notificationId, timeZone, commuteBufferMin, now } = props
  const [result, setResult] = useState<{ key: string; data: NotificationPackage | null; error: string | null } | null>(null)
  const key = `${recommendation.evaluation_id}:${notificationId ?? 'preview'}`

  useEffect(() => {
    let cancelled = false
    const request = notificationId ? getNotification(notificationId) : getPackagePreview(recommendation.evaluation_id)
    request
      .then((data) => !cancelled && setResult({ key, data, error: null }))
      .catch((error: unknown) => {
        if (!cancelled) setResult({ key, data: null, error: error instanceof Error ? error.message : 'Unknown error' })
      })
    return () => {
      cancelled = true
    }
  }, [key, notificationId, recommendation.evaluation_id])

  const current = result?.key === key ? result : null
  const nowMinutes = facilityMinutes(now, timeZone)
  const recipients = new Map((current?.data?.package.recipients ?? []).map((r) => [r.employee_id, r]))
  const messages = new Map((current?.data?.package.messages ?? []).map((m) => [m.id, m]))
  const warnings = current?.data?.package.warnings ?? []

  return (
    <section aria-label="Who gets told what" className="rounded-xl bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-bold text-slate-950">Who gets told what</h2>
        <p className="text-sm text-slate-600">
          {notificationId ? 'As sent' : 'If approved now'}: {postureTheme[recommendation.posture].label.toLowerCase()} ·{' '}
          {employees.length} people on the roster (synthetic names)
        </p>
      </div>

      {current?.error && (
        <p className="mt-3 rounded-md border-2 border-red-600 bg-red-50 p-3 text-sm text-red-900" role="alert">
          Could not load the notification package: {current.error}
        </p>
      )}
      {!current && <p className="mt-3 text-sm text-slate-600">Building the notification package…</p>}

      {warnings.length > 0 && (
        <div className="mt-3 rounded-lg border-2 border-amber-400 bg-amber-50 p-3 text-sm text-amber-900" role="alert">
          <p className="font-bold">Check before sending ({warnings.length})</p>
          <ul className="mt-1 list-disc pl-5">
            {warnings.map((warning, index) => (
              <li key={`${warning.type}-${warning.message_id ?? index}`}>{warning.text}</li>
            ))}
          </ul>
        </div>
      )}

      {current?.data &&
        timingSections.map((section) => {
          const people = employees
            .filter((employee) => timingOf(employee, nowMinutes) === section.id)
            .sort((a, b) => toMinutes(a.shift_start) - toMinutes(b.shift_start))
          if (people.length === 0) return null
          return (
            <div className="mt-5" key={section.id}>
              <h3 className="font-bold text-slate-950">
                {section.title} <span className="font-normal text-slate-500">({people.length}) · {section.note}</span>
              </h3>
              <ul className="mt-2 divide-y divide-slate-100">
                {groupsIn(people).map(([group, members]) => (
                  <GroupRow
                    commuteBufferMin={commuteBufferMin}
                    group={group}
                    key={group}
                    members={members}
                    messages={messages}
                    nowMinutes={nowMinutes}
                    recipients={recipients}
                    timing={section.id}
                  />
                ))}
              </ul>
            </div>
          )
        })}
    </section>
  )
}

// One row per roster group inside a timing section, so hundreds of people stay readable.
function groupsIn(people: Employee[]): [string, Employee[]][] {
  const byGroup = new Map<string, Employee[]>()
  for (const person of people) byGroup.set(person.group, [...(byGroup.get(person.group) ?? []), person])
  const order = employeeGroups.map((group) => group.id as string)
  return [...byGroup.entries()].sort(([a], [b]) => (order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99))
}

type PackageMessage = NotificationPackage['package']['messages'][number]

type GroupRowProps = {
  group: string
  members: Employee[]
  recipients: Map<string, PackageRecipient>
  messages: Map<string, PackageMessage>
  timing: Timing
  nowMinutes: number
  commuteBufferMin: number
}

function GroupRow({ group, members, recipients, messages, timing, nowMinutes, commuteBufferMin }: GroupRowProps) {
  const included = members.filter((member) => recipients.get(member.employee_id)?.included)
  const first = recipients.get((included[0] ?? members[0]).employee_id)
  // The standard-language message is what the group is told; variants are counted next to it.
  const groupMessages = included.map((member) => messages.get(recipients.get(member.employee_id)?.message_id ?? ''))
  const standard = groupMessages.find((message) => message && message.variant === 'standard') ?? groupMessages[0]
  const variants = groupMessages.filter((message) => message && message.variant && message.variant !== 'standard')
  const spanish = variants.filter((message) => message?.variant === 'spanish').length
  const largePrint = variants.length - spanish
  const leaveHome = Math.min(...members.map((member) => toMinutes(member.shift_start))) - commuteBufferMin
  const tellByPassed = timing === 'arriving' && nowMinutes >= leaveHome

  return (
    <li className="py-3 text-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p>
          <span className="font-semibold text-slate-950">{groupLabel(group)}</span>
          <span className="text-slate-600"> · {members.length} {members.length === 1 ? 'person' : 'people'}</span>
        </p>
        {timing === 'arriving' && included.length > 0 && (
          <span className={`text-xs font-semibold ${tellByPassed ? 'text-red-700' : 'text-slate-700'}`}>
            {tellByPassed ? 'Past tell-by: some may already be travelling' : `Tell by ${clock(leaveHome)} (first to leave home)`}
          </span>
        )}
      </div>
      {included.length > 0 ? (
        <p className="mt-1 text-slate-700">
          <span className="font-medium">Told: </span>
          {standard ? (whatToDo(standard.text) ?? 'see message') : 'message pending'}
          <span className="text-slate-500"> · {(first?.channel_plan ?? []).join(' → ')}</span>
          {spanish > 0 && <span className="ml-1 rounded bg-slate-100 px-1.5 py-0.5 text-xs">{spanish} Spanish</span>}
          {largePrint > 0 && <span className="ml-1 rounded bg-slate-100 px-1.5 py-0.5 text-xs">{largePrint} large print</span>}
        </p>
      ) : (
        <p className="mt-1 text-slate-500">Not notified · {first?.reason ?? 'not in this package'}</p>
      )}
      <details className="mt-1">
        <summary className="cursor-pointer text-xs text-blue-700">
          {standard ? 'People and full message' : 'People'}
        </summary>
        {standard && (
          <p className="mt-1 whitespace-pre-line rounded bg-slate-50 p-2 text-xs text-slate-800">{standard.text}</p>
        )}
        <ul className="mt-1 columns-1 text-xs text-slate-700 sm:columns-2">
          {members.map((member) => (
            <li key={member.employee_id}>
              {member.name} · {clock(toMinutes(member.shift_start))}–{clock(toMinutes(member.shift_end))}
              {timing === 'arriving' && ` · tell by ${clock(toMinutes(member.shift_start) - commuteBufferMin)}`}
            </li>
          ))}
        </ul>
      </details>
    </li>
  )
}
