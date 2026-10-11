import type { Recommendation, RecommendationInput } from './types'

export type AlertTierName = 'warning' | 'watch' | 'advisory'

export type AlertSummary = {
  event: string
  severity?: string
  certainty?: string
  urgency?: string
  tier?: string
  onset?: string | null
  ends?: string | null
}

export const findInput = (recommendation: Recommendation, text: string) =>
  recommendation.inputs.find((input) => input.source.toLowerCase().includes(text))

// The backend sends a list of alerts; contract fixtures send one alert object with the label as the event.
export function alertsFrom(input: RecommendationInput | undefined): AlertSummary[] {
  if (!input) return []
  if (Array.isArray(input.value)) return input.value as AlertSummary[]
  if (input.value && typeof input.value === 'object') return [{ event: input.label, ...(input.value as object) }]
  return []
}

// Same rule as the backend normalizer: the event name's wording decides the tier, not severity alone.
export function alertTier(alert: AlertSummary): AlertTierName {
  const tier = alert.tier?.toLowerCase()
  if (tier === 'warning' || tier === 'watch' || tier === 'advisory') return tier
  const event = alert.event.toLowerCase()
  if (event.includes('warning') || event.includes('emergency')) return 'warning'
  if (event.includes('watch')) return 'watch'
  return 'advisory'
}

export const tierRank: Record<AlertTierName, number> = { warning: 0, watch: 1, advisory: 2 }
