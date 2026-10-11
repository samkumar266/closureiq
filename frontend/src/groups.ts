import type { EmployeeGroup } from './types'

// Order and wording follow the "Who is told what" table in the architecture doc.
// detail_in is not a contract group, but the backend roster sends it; the architecture treats it as assigned.
export const employeeGroups: { id: EmployeeGroup | 'detail_in'; label: string; note: string }[] = [
  { id: 'essential', label: 'Essential', note: 'Reports regardless of posture' },
  { id: 'onsite_telework_eligible', label: 'Onsite, telework-eligible', note: 'Follows the posture or teleworks' },
  { id: 'onsite_not_telework_eligible', label: 'Onsite, not telework-eligible', note: 'Must report or take leave' },
  { id: 'detail_in', label: 'Detailed in from another office', note: 'Treated as assigned' },
  { id: 'already_teleworking', label: 'Already teleworking', note: 'Usually no change' },
  { id: 'contractor', label: 'Contractors', note: 'Work status goes through the contract lead' },
  { id: 'detail_elsewhere', label: 'On detail elsewhere', note: 'Excluded, with the reason shown' },
  { id: 'on_leave_or_off', label: 'On leave or off today', note: 'Excluded, with the reason shown' },
]

export function groupLabel(group: string) {
  return employeeGroups.find((item) => item.id === group)?.label ?? group.replaceAll('_', ' ')
}
