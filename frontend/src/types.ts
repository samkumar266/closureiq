import type { Posture } from './theme'

// Shapes from docs/contract.md. A field that may be empty is null, never missing.

export type ConfidenceLevel = 'high' | 'medium' | 'low'
export type DataMode = 'live' | 'replay'
export type AlertTier = 'none' | 'advisory' | 'watch' | 'warning'
export type SourceHealth = 'ok' | 'degraded' | 'missing'
export type ApprovalStatus = 'not_required' | 'pending' | 'approved' | 'rejected' | 'overridden' | 'unresolved'

export type RecommendationInput = {
  id: string
  role: 'drove' | 'context'
  source: string
  label: string
  // The live backend also sends lists (active alerts, hourly periods) here.
  value: number | Record<string, unknown> | unknown[] | null
  unit?: string
  onset?: string
  ends?: string
  fetched_at: string
  snapshot_id: string
  stale: boolean
}

// Tier and field thresholds (T1 to T3) have string cutoffs; numeric ones add unit, margin and anchor.
export type ThresholdCrossed = {
  id: string
  input_id: string
  cutoff: string | number
  actual: string | number
  unit?: string
  margin?: number
  anchor?: string
  anchor_url?: string | null
}

export type ThresholdNotCrossed = {
  id: string
  input_id: string
  cutoff: string | number
  actual: string | number
  unit?: string
  distance?: number
}

export type MissingEvidence = {
  source: string
  reason: string
  last_good_snapshot_id: string | null
  last_good_age_minutes: number | null
  max_age_minutes: number
}

export type FlipListItem = {
  change: string
  resulting_posture: Posture
  note?: string
}

export type RecommendationParameters = {
  monitoring?: 'normal' | 'elevated'
  delay_until?: string
  dismiss_at?: string
  closed_from?: string
  closed_until?: string
  next_update?: string
}

export type Recommendation = {
  hypothetical: boolean
  evaluation_id: string
  supersedes: string | null
  facility_id: string
  evaluated_at: string
  policy_version: string
  data_mode: DataMode
  posture: Posture
  raw_posture: Posture
  held_by_hysteresis: boolean
  parameters: RecommendationParameters
  safety_instruction: string | null
  decision_deadline: string | null
  confidence: {
    level: ConfidenceLevel
    reasons: string[]
  }
  inputs: RecommendationInput[]
  thresholds_crossed: ThresholdCrossed[]
  thresholds_not_crossed: ThresholdNotCrossed[]
  missing_evidence: MissingEvidence[]
  flip_list: FlipListItem[]
  rationale: string
}

export type Facility = {
  facility_id: string
  name: string
  location: {
    lat: number
    lon: number
    timezone: string
  }
  highest_alert_tier: AlertTier
  // Optional, not yet sent by the backend: the alert behind highest_alert_tier, for the Watchlist card.
  top_alert?: { event: string; severity: string | null; certainty: string | null } | null
  source_health: SourceHealth
  data_mode: DataMode
  // null until the backend has evaluated the facility for the first time.
  current: FacilityCurrent | null
}

export type FacilityCurrent = {
  evaluation_id: string
  posture: Posture
  confidence: ConfidenceLevel
  evaluated_at: string
  decision_deadline: string | null
  headline: string
  approval_status: ApprovalStatus
}

export type SourceStatus = {
  source: string
  status: 'fresh' | 'stale' | 'missing'
  fetched_at: string | null
  age_seconds: number | null
  max_age_seconds: number
}

export type Approval = {
  id: string
  evaluation_id: string
  action: 'approve' | 'reject' | 'override'
  final_posture: Posture
  actor: string
  reason: string | null
  acted_at_wall: string
  acted_at_sim?: string
}

export type FacilityStatus = {
  facility_id: string
  evaluation: Recommendation
  approval: Approval | null
  notification_id: string | null
  sources: SourceStatus[]
}

export type EmployeeGroup =
  | 'essential'
  | 'onsite_telework_eligible'
  | 'onsite_not_telework_eligible'
  | 'already_teleworking'
  | 'detail_elsewhere'
  | 'on_leave_or_off'
  | 'contractor'

export type ChannelType = 'email' | 'sms' | 'push' | 'voice'

export type Employee = {
  employee_id: string
  name: string
  group: EmployeeGroup
  // Free text: the seed roster and the backend use different values (onsite vs assigned, and so on).
  assignment_type: string
  shift_start: string
  shift_end: string
  work_status_today: string
  essential: boolean
  telework_eligible: boolean
  commute_county: string
  // Contract: objects. The backend roster currently sends plain channel names.
  channels: ({ type: ChannelType; address: string } | string)[]
  comm_needs: string[]
  supervisor_id: string | null
}

export type ApprovalResponse = {
  approval: Approval
  notification_id: string | null
}

export type PackageRecipient = {
  employee_id: string
  included: boolean
  // string, not EmployeeGroup: the backend also sends detail_in.
  group: string
  reason: string
  message_id?: string
  channel_plan?: ChannelType[]
}

export type DeliveryStatus = 'queued' | 'sent' | 'delivered' | 'simulated' | 'failed' | 'acknowledged'

export type Delivery = {
  delivery_id: string
  recipient_id: string
  channel: ChannelType
  real: boolean
  status: DeliveryStatus
  status_at_wall: string
}

export type EscalationStep = {
  step: string
  label: string
  due_sim: string
  fired_at_sim: string | null
}

// Same shape for GET /package-preview (preview: true) and GET /api/notifications/{id}.
export type PackageMessage = {
  id: string
  group: string
  text: string
  variant?: 'standard' | 'large_print' | 'spanish'
  needs_translation?: boolean
}

export type PackageWarning = {
  type: 'needs_translation' | 'missing_parameters' | 'derived_parameters'
  message_id: string | null
  group: string | null
  variant: string | null
  employee_ids: string[]
  text: string
}

export type NotificationPackage = {
  notification_id: string | null
  evaluation_id: string
  approval_id: string | null
  standing_policy: 'shelter_in_place' | null
  preview: boolean
  ack_deadline: string | null
  next_update: string | null
  package: {
    recipients: PackageRecipient[]
    messages: PackageMessage[]
    // Added to the contract by notify: problems the approver must see before approving.
    warnings?: PackageWarning[]
  }
  deliveries: Delivery[]
  escalation: EscalationStep[]
}

export type WhatIfResponse = {
  hypothetical: true
  whatif_id: string
  based_on: string
  result: Recommendation
  changed_fields: string[]
}

export type ReplayResult = {
  identical: boolean
  diff: { path: string; stored: unknown; replayed: unknown }[]
}

export type DecisionRecord = {
  evaluation: Recommendation
  chain: string[]
  evidence: {
    snapshot_id: string
    source: string
    url: string
    fetched_at_wall: string
    fetched_at_sim: string
    http_status: number | null
    ok: boolean
    raw_payload: unknown
    error?: string | null
  }[]
  approval: Approval | null
  // Inside the record the backend names the id field `id` rather than `notification_id`.
  notification: (Partial<NotificationPackage> & { id?: string; created_at_wall?: string }) | null
  deliveries: (Delivery & { status_history: { status: DeliveryStatus; at_wall: string; at_sim: string }[] })[]
  timers: Record<string, unknown>[]
  audit_log: Record<string, unknown>[]
}
