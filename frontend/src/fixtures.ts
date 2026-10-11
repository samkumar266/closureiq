import facilitiesFixture from './mock-data/facilities.json'
import type {
  AlertTier,
  ConfidenceLevel,
  DataMode,
  Facility,
  SourceHealth,
} from './types'
import type { Posture } from './theme'

type FixtureFacility = Omit<Facility, 'highest_alert_tier' | 'source_health' | 'data_mode' | 'current'> & {
  highest_alert_tier: string
  source_health: string
  data_mode: string
  current: Omit<Facility['current'], 'posture' | 'confidence'> & {
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
