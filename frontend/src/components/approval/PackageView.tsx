import { groupLabel } from '../../groups'
import type { Employee, NotificationPackage } from '../../types'

type PackageViewProps = {
  notification: NotificationPackage
  employees: Employee[]
}

// Who is told what and why: included and excluded people with reasons, messages and channel routing.
export function PackageView({ notification, employees }: PackageViewProps) {
  const { recipients, messages } = notification.package
  const warnings = notification.package.warnings ?? []
  const nameOf = (employeeId: string) =>
    employees.find((employee) => employee.employee_id === employeeId)?.name ?? employeeId
  const included = recipients.filter((recipient) => recipient.included)
  const excluded = recipients.filter((recipient) => !recipient.included)

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-700">
        <strong>{included.length}</strong> people will be notified and <strong>{excluded.length}</strong> are excluded.
        Only email can really send; every other channel is simulated.
      </p>

      {warnings.length > 0 && (
        <section className="rounded-lg border-2 border-amber-400 bg-amber-50 p-3" role="alert">
          <h3 className="font-bold text-amber-900">Check before sending ({warnings.length})</h3>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-amber-900">
            {warnings.map((warning, index) => (
              <li key={`${warning.type}-${warning.message_id ?? index}`}>
                {warning.text}
                {warning.employee_ids.length > 0 && <> ({warning.employee_ids.map(nameOf).join(', ')})</>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h3 className="font-bold text-slate-950">Drafted messages</h3>
        {messages.length === 0 ? (
          <p className="mt-1 text-sm text-slate-600">No messages: nobody is included.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {messages.map((message) => {
              const count = included.filter((recipient) => recipient.message_id === message.id).length
              return (
                <li className="rounded-lg border border-slate-200 bg-slate-50 p-3" key={message.id}>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {groupLabel(message.group)} · {count} {count === 1 ? 'person' : 'people'}
                    {message.variant && message.variant !== 'standard' && (
                      <span className="ml-2 rounded bg-slate-200 px-1.5 py-0.5 normal-case text-slate-700">
                        {message.variant === 'spanish' ? 'Spanish' : 'Large print'}
                      </span>
                    )}
                    {message.needs_translation && (
                      <span className="ml-2 rounded bg-red-100 px-1.5 py-0.5 normal-case text-red-800">
                        Needs translation: English shown
                      </span>
                    )}
                  </p>
                  <p className="mt-1 whitespace-pre-line text-sm text-slate-800">{message.text}</p>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <section>
        <h3 className="font-bold text-slate-950">Included</h3>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="py-1 pr-3">Name</th>
                <th className="py-1 pr-3">Group</th>
                <th className="py-1 pr-3">Channels, in order</th>
                <th className="py-1">Why</th>
              </tr>
            </thead>
            <tbody>
              {included.map((recipient) => (
                <tr className="border-t border-slate-100 align-top" key={recipient.employee_id}>
                  <td className="py-1.5 pr-3 font-medium text-slate-900">{nameOf(recipient.employee_id)}</td>
                  <td className="py-1.5 pr-3 text-slate-700">{groupLabel(recipient.group)}</td>
                  <td className="py-1.5 pr-3 text-slate-700">{(recipient.channel_plan ?? []).join(' → ')}</td>
                  <td className="py-1.5 text-slate-600">{recipient.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {excluded.length > 0 && (
        <section>
          <h3 className="font-bold text-slate-950">Excluded</h3>
          <ul className="mt-2 space-y-1 text-sm">
            {excluded.map((recipient) => (
              <li key={recipient.employee_id}>
                <span className="font-medium text-slate-900">{nameOf(recipient.employee_id)}</span>{' '}
                <span className="text-slate-600">· {recipient.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
