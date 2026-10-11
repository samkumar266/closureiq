// Display helpers. Times are shown in the facility's timezone (contract: conventions).

export function formatTime(iso: string, timeZone: string) {
  return new Date(iso).toLocaleTimeString([], { timeZone, hour: 'numeric', minute: '2-digit', timeZoneName: 'short' })
}

export function formatDateTime(iso: string, timeZone: string) {
  return new Date(iso).toLocaleString([], {
    timeZone,
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  })
}

// Rounds float noise such as 0.15000000000000002 without hiding real precision.
export function formatNumber(value: number) {
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(2)))
}

export function formatDuration(totalSeconds: number) {
  const seconds = Math.max(0, Math.round(totalSeconds))
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  if (hours < 48) return `${hours} h ${minutes % 60} min`
  return `${Math.floor(hours / 24)} days`
}

export function formatCountdown(deadline: string, now: number) {
  const remainingMilliseconds = new Date(deadline).getTime() - now
  if (remainingMilliseconds <= 0) {
    return 'Decision deadline passed'
  }
  const totalSeconds = Math.floor(remainingMilliseconds / 1_000)
  const hours = Math.floor(totalSeconds / 3_600)
  const minutes = Math.floor((totalSeconds % 3_600) / 60)
  const seconds = totalSeconds % 60
  return `${hours}h ${minutes}m ${seconds}s remaining`
}

// Evidence values can be a number, a flat object (alert fields) or, from the live backend,
// a list (active alerts, hourly periods) or nested objects (gridpoint series). Summarise those.
export function formatValue(value: unknown, unit?: string): string {
  if (value === null || value === undefined) return 'No value'
  if (typeof value === 'number') return `${formatNumber(value)}${unit ? ` ${unit}` : ''}`
  if (Array.isArray(value)) return value.length === 0 ? 'None active' : `${value.length} entries`
  if (typeof value !== 'object') return String(value)
  return Object.entries(value)
    .filter(([, item]) => item !== null && item !== undefined && item !== '')
    .map(([key, item]) => {
      const label = key.replaceAll('_', ' ')
      if (Array.isArray(item)) return `${label}: ${item.length} values`
      if (typeof item === 'object') return `${label}: …`
      return `${label}: ${typeof item === 'number' ? formatNumber(item) : String(item)}`
    })
    .join(' · ')
}
