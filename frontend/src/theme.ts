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
    // DEPRECATED(closureiq): orange moved to telework so the five postures form one ramp.
    // color: '#ea580c',
    color: '#d97706',
  },
  unscheduled_leave_or_telework: {
    label: 'Unscheduled leave or telework',
    // DEPRECATED(closureiq): blue broke the green-to-red ramp of the graded posture scale.
    // color: '#2563eb',
    color: '#c2410c',
  },
  closure: {
    label: 'Closure',
    color: '#dc2626',
  },
}

// Mildest first, the order in api/engine/policy.yaml. The graded scale and its colour ramp follow it.
export const postureOrder: Posture[] = [
  'normal_operations',
  'delayed_arrival',
  'early_dismissal',
  'unscheduled_leave_or_telework',
  'closure',
]
