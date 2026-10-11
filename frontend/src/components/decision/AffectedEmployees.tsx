import type { Employee, EmployeeGroup } from '../../types'

type AffectedEmployeesProps = {
  employees: Employee[]
}

// Order and wording follow the "Who is told what" table in the architecture doc.
// detail_in is not a contract group, but the backend roster sends it; the architecture treats it as assigned.
const groups: { id: EmployeeGroup | 'detail_in'; label: string; note: string }[] = [
  { id: 'essential', label: 'Essential', note: 'Reports regardless of posture' },
  { id: 'onsite_telework_eligible', label: 'Onsite, telework-eligible', note: 'Follows the posture or teleworks' },
  { id: 'onsite_not_telework_eligible', label: 'Onsite, not telework-eligible', note: 'Must report or take leave' },
  { id: 'detail_in', label: 'Detailed in from another office', note: 'Treated as assigned' },
  { id: 'already_teleworking', label: 'Already teleworking', note: 'Usually no change' },
  { id: 'contractor', label: 'Contractors', note: 'Work status goes through the contract lead' },
  { id: 'detail_elsewhere', label: 'On detail elsewhere', note: 'Excluded, with the reason shown' },
  { id: 'on_leave_or_off', label: 'On leave or off today', note: 'Excluded, with the reason shown' },
]

export function AffectedEmployees({ employees }: AffectedEmployeesProps) {
  // Anyone in a group not listed above still shows up, so nobody silently disappears.
  const knownGroups = new Set<string>(groups.map((group) => group.id))
  const ungrouped = employees.filter((employee) => !knownGroups.has(employee.group))
  const sections = [
    ...groups.map((group) => ({ ...group, members: employees.filter((employee) => employee.group === group.id) })),
    { id: 'other', label: 'Other', note: 'Group not recognised by the UI', members: ungrouped },
  ]

  return (
    <section aria-label="Affected employees" className="rounded-xl bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-bold text-slate-950">Affected employees by group</h2>
        <p className="text-sm text-slate-600">{employees.length} people on the roster (synthetic names)</p>
      </div>
      {employees.length === 0 ? (
        <p className="mt-3 text-sm text-slate-600">No roster available for this facility.</p>
      ) : (
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {sections.map(({ members, ...group }) => {
            if (members.length === 0) return null
            return (
              <details className="rounded-lg border border-slate-200 p-3" key={group.id}>
                <summary className="cursor-pointer">
                  <span className="text-2xl font-bold text-slate-950">{members.length}</span>{' '}
                  <span className="font-semibold text-slate-900">{group.label}</span>
                  <span className="block text-xs text-slate-500">{group.note}</span>
                </summary>
                <ul className="mt-2 space-y-1 text-sm text-slate-800">
                  {members.map((employee) => (
                    <li key={employee.employee_id}>
                      {employee.name}{' '}
                      <span className="text-xs text-slate-500">
                        {employee.shift_start}–{employee.shift_end}
                        {employee.comm_needs.length > 0 && ' · alternate format or language'}
                      </span>
                    </li>
                  ))}
                </ul>
              </details>
            )
          })}
        </div>
      )}
    </section>
  )
}
