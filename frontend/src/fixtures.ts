import facilitiesFixture from './mock-data/facilities.json'
import type {
  AlertTier,
  ConfidenceLevel,
  DataMode,
  Employee,
  Facility,
  FacilityCurrent,
  Recommendation,
  SourceHealth,
  SourceStatus,
} from './types'
import type { Posture } from './theme'

type FixtureFacility = Omit<Facility, 'highest_alert_tier' | 'source_health' | 'data_mode' | 'current'> & {
  highest_alert_tier: string
  source_health: string
  data_mode: string
  current: Omit<FacilityCurrent, 'posture' | 'confidence'> & {
    posture: string
    confidence: string
  }
}

type FacilitiesFixture = {
  facilities: FixtureFacility[]
}

const postureValues: Posture[] = [
  'normal_operations',
  'delayed_arrival',
  'early_dismissal',
  'unscheduled_leave_or_telework',
  'closure',
]
const alertTiers: AlertTier[] = ['none', 'advisory', 'watch', 'warning']
const sourceHealthValues: SourceHealth[] = ['ok', 'degraded', 'missing']
const dataModes: DataMode[] = ['live', 'replay']
const confidenceLevels: ConfidenceLevel[] = ['high', 'medium', 'low']

function includes<T extends string>(values: readonly T[], value: string): value is T {
  return values.includes(value as T)
}

function normalizeFacility(facility: FixtureFacility): Facility {
  const { current } = facility

  if (!includes(postureValues, current.posture)) {
    throw new Error(`Unsupported posture in facilities fixture: ${current.posture}`)
  }
  if (!includes(alertTiers, facility.highest_alert_tier)) {
    throw new Error(`Unsupported alert tier in facilities fixture: ${facility.highest_alert_tier}`)
  }
  if (!includes(sourceHealthValues, facility.source_health)) {
    throw new Error(`Unsupported source health in facilities fixture: ${facility.source_health}`)
  }
  if (!includes(dataModes, facility.data_mode)) {
    throw new Error(`Unsupported data mode in facilities fixture: ${facility.data_mode}`)
  }
  if (!includes(confidenceLevels, current.confidence)) {
    throw new Error(`Unsupported confidence in facilities fixture: ${current.confidence}`)
  }

  return {
    ...facility,
    highest_alert_tier: facility.highest_alert_tier,
    source_health: facility.source_health,
    data_mode: facility.data_mode,
    current: {
      ...current,
      posture: current.posture,
      confidence: current.confidence,
    },
  }
}

export const facilities = (facilitiesFixture as FacilitiesFixture).facilities.map(normalizeFacility)

export function loadFacilities(): Facility[] {
  return structuredClone(facilities)
}

// Recommendation fixtures, used by the Facility screen while the backend is not running.
const recommendationModules = import.meta.glob<{ default: unknown }>(
  ['./mock-data/*.json', '!./mock-data/facilities.json'],
  { eager: true },
)
const recommendations = Object.values(recommendationModules).map((module) => module.default as Recommendation)

const rosterModules = import.meta.glob<{ default: { employees: Employee[] } }>('./mock-data/seed/roster_*.json', {
  eager: true,
})

// Picks the facility's current evaluation from facilities.json, else any fixture for that facility.
export function loadRecommendation(facilityId: string): Recommendation | null {
  const currentId = facilities.find((facility) => facility.facility_id === facilityId)?.current?.evaluation_id
  const match =
    recommendations.find((item) => item.evaluation_id === currentId) ??
    recommendations.find((item) => item.facility_id === facilityId)
  return match ? structuredClone(match) : null
}

export function loadRoster(facilityId: string): Employee[] {
  const module = rosterModules[`./mock-data/seed/roster_${facilityId}.json`]
  return module ? structuredClone(module.default.employees) : []
}

// Fixtures have no source list, so derive one from the inputs and the missing evidence.
export function sourcesFromRecommendation(recommendation: Recommendation): SourceStatus[] {
  const missingSources = new Set(recommendation.missing_evidence.map((item) => item.source))
  const fromInputs = recommendation.inputs.map((input) => ({
    source: input.source,
    status: missingSources.has(input.source) ? ('missing' as const) : input.stale ? ('stale' as const) : ('fresh' as const),
    fetched_at: input.fetched_at,
    age_seconds: (new Date(recommendation.evaluated_at).getTime() - new Date(input.fetched_at).getTime()) / 1_000,
    max_age_seconds: 0,
  }))
  const withoutInputs = recommendation.missing_evidence
    .filter((item) => !recommendation.inputs.some((input) => input.source === item.source))
    .map((item) => ({
      source: item.source,
      status: 'missing' as const,
      fetched_at: null,
      age_seconds: item.last_good_age_minutes === null ? null : item.last_good_age_minutes * 60,
      max_age_seconds: item.max_age_minutes * 60,
    }))
  return [...fromInputs, ...withoutInputs]
}
