// Plain-language names for the policy thresholds (architecture "Thresholds and where they come from").
// The id (T1...T11) is kept only as a tooltip so the record stays traceable to docs/thresholds.md.
export const thresholdNames: Record<string, string> = {
  T1: 'Alert level is a Warning',
  T2: 'Severity is Severe or Extreme',
  T3: 'Certainty is Likely or Observed',
  T4: 'Wind gusts of 58 mph or more',
  T5: 'Sustained wind of 40 mph or more',
  T6: 'Ice of 0.25 in or more',
  T7: 'River at minor flood stage',
  T8: 'River at moderate flood stage',
  T9: 'River at action stage',
  T10: 'One-hour clearing buffer after the hazard',
  T11: 'Commute and notification lead times',
}

export const thresholdName = (id: string) => thresholdNames[id] ?? id

// Short nouns for use inside a sentence when tidying agent answers ("crossed warning level, severity and
// certainty"). No numbers here: the agent's sentence already states the cutoff.
export const thresholdShortNames: Record<string, string> = {
  T1: 'warning level',
  T2: 'severity',
  T3: 'certainty',
  T4: 'gust threshold',
  T5: 'sustained-wind threshold',
  T6: 'ice threshold',
  T7: 'minor flood stage',
  T8: 'moderate flood stage',
  T9: 'action stage',
  T10: 'clearing buffer',
  T11: 'commute and notification lead times',
}
