import type { Posture } from './theme'

export type ConfidenceLevel = 'high' | 'medium' | 'low'
export type DataMode = 'live' | 'replay'
export type AlertTier = 'none' | 'advisory' | 'watch' | 'warning'
export type SourceHealth = 'ok' | 'degraded' | 'missing'

export type RecommendationInput = {
  id: string
  role: string
  source: string
  label: string
  value: unknown
  unit?: string
  fetched_at: string
  snapshot_id: string
  stale: boolean
}

export type Threshold = {
  id: string
  [key: string]: unknown
}

export type MissingEvidence = {
  source: string
  reason: string
  [key: string]: unknown
}

export type FlipListItem = {
  change: string
  resulting_posture: string
  note?: string
}

export type Recommendation = {
  evaluation_id: string
  supersedes: string | null
  facility_id: string
  evaluated_at: string
  policy_version: string
  data_mode: DataMode
  posture: Posture
  parameters: Record<string, unknown>
  safety_instruction: string | null
  decision_deadline: string | null
  confidence: {
    level: ConfidenceLevel
    reasons: string[]
  }
  inputs: RecommendationInput[]
  thresholds_crossed: Threshold[]
  thresholds_not_crossed: Threshold[]
  missing_evidence: MissingEvidence[]
  flip_list: FlipListItem[]
  rationale: string
}

export type Facility = {
  facility_id: string
  name: string
  highest_alert_tier: AlertTier
  source_health: SourceHealth
  data_mode: DataMode
  current: {
    evaluation_id: string
    posture: Posture
    confidence: ConfidenceLevel
    evaluated_at: string
    decision_deadline: string | null
    headline: string
    approval_status: string
  }
}
