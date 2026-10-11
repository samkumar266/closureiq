import { alertsFrom, findInput } from '../../alerts'
import { formatNumber, formatTime } from '../../format'
import type { Recommendation, RecommendationInput } from '../../types'

type WeatherWidgetProps = {
  recommendation: Recommendation
  facilityName: string
  timeZone: string
  now: number
}

type HourlyPeriod = {
  start_time: string
  end_time: string
  temperature: number
  temperature_unit: string
  wind_speed: string
  wind_direction: string
  precipitation_probability: number | null
  short_forecast: string
}

// Highest forecast gust in the next 12 hours from the gridpoint windGust series.
function maxGust(input: RecommendationInput | undefined, now: number) {
  const series = (input?.value as { windGust?: { value: number; valid_time: string }[] } | null)?.windGust
  if (!Array.isArray(series)) return null
  const horizon = now + 12 * 3_600_000
  const values = series
    .filter((item) => {
      const start = new Date(item.valid_time.split('/')[0]).getTime()
      return start <= horizon && start >= now - 3_600_000
    })
    .map((item) => item.value)
  return values.length ? Math.max(...values) : null
}

function Fetched({ input, timeZone }: { input: RecommendationInput; timeZone: string }) {
  return (
    <span className="text-xs text-sky-200">
      {input.source} · fetched {formatTime(input.fetched_at, timeZone)}
    </span>
  )
}

// Phone-widget style summary of current conditions. Every number comes from the evaluation's stored
// inputs (architecture: the dashboard renders the recommendation object and nothing else).
export function WeatherWidget({ recommendation, facilityName, timeZone, now }: WeatherWidgetProps) {
  const alertsInput = findInput(recommendation, 'alert')
  const hourlyInput = findInput(recommendation, 'hourly')
  const gridInput = findInput(recommendation, 'forecast grid')
  const alerts = alertsFrom(alertsInput)
  const periods = Array.isArray(hourlyInput?.value) ? (hourlyInput.value as HourlyPeriod[]) : []
  const currentIndex = Math.max(
    0,
    periods.findIndex((period) => new Date(period.end_time).getTime() > now),
  )
  const current = periods[currentIndex]
  const upcoming = periods.slice(currentIndex, currentIndex + 6)
  const gust = maxGust(gridInput, now)

  return (
    <section
      aria-label="Current weather"
      className="rounded-2xl bg-gradient-to-br from-sky-700 to-slate-800 p-5 text-white shadow-md"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-sky-100">{facilityName}</p>
          {current ? (
            <>
              <p className="mt-1 text-5xl font-light">
                {current.temperature}°{current.temperature_unit}
              </p>
              <p className="mt-1 text-lg">{current.short_forecast}</p>
            </>
          ) : (
            <p className="mt-2 text-sm text-sky-100">NWS hourly forecast not available in this evaluation.</p>
          )}
        </div>
        {current && (
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
            <dt className="text-sky-200">Wind</dt>
            <dd>
              {current.wind_speed} {current.wind_direction}
            </dd>
            <dt className="text-sky-200">Gusts, next 12 h</dt>
            <dd>{gust === null ? 'n/a' : `up to ${formatNumber(gust)} mph`}</dd>
            <dt className="text-sky-200">Rain chance</dt>
            <dd>{current.precipitation_probability ?? 0}%</dd>
          </dl>
        )}
      </div>

      {upcoming.length > 0 && (
        <ol className="mt-4 grid grid-cols-6 gap-2 border-t border-white/20 pt-3 text-center text-xs">
          {upcoming.map((period) => (
            <li key={period.start_time}>
              <p className="text-sky-200">{formatTime(period.start_time, timeZone).replace(/:00| [A-Z]{2,4}$/g, '')}</p>
              <p className="mt-1 text-base">{period.temperature}°</p>
              <p className="text-sky-200">{period.precipitation_probability ?? 0}%</p>
            </li>
          ))}
        </ol>
      )}

      <div className="mt-4 border-t border-white/20 pt-3">
        {/* Alerts are listed in their own section below the widget (AlertList), coloured by tier. */}
        {alerts.length === 0 ? (
          <p className="text-sm font-semibold text-emerald-300">No active NWS alerts</p>
        ) : (
          <p className="text-sm font-semibold text-amber-200">
            {alerts.length} active NWS {alerts.length === 1 ? 'alert' : 'alerts'} ↓
          </p>
        )}
        <p className="mt-2 flex flex-wrap gap-x-3">
          {[alertsInput, hourlyInput, gridInput].map(
            (input) => input && <Fetched input={input} key={input.id} timeZone={timeZone} />,
          )}
        </p>
      </div>
    </section>
  )
}
