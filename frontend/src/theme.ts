export type Posture =
  | 'normal_operations'
  | 'delayed_arrival'
  | 'early_dismissal'
  | 'unscheduled_leave_or_telework'
  | 'closure'

export type PostureTheme = {
  label: string
  color: string
}

export const postureTheme: Record<Posture, PostureTheme> = {
  normal_operations: {
    label: 'Normal operations',
    color: '#16a34a',
  },
  delayed_arrival: {
    label: 'Delayed arrival',
    color: '#ca8a04',
  },
  early_dismissal: {
    label: 'Early dismissal',
    color: '#ea580c',
  },
  unscheduled_leave_or_telework: {
    label: 'Unscheduled leave or telework',
    color: '#2563eb',
  },
  closure: {
    label: 'Closure',
    color: '#dc2626',
  },
}
