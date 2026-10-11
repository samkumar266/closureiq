import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { evaluateFacility, getFacilities, setClock, setDataMode } from '../api'
import { requestClockRefresh, useServerClock } from '../hooks/useServerClock'

const DEMO_KEY = 'closureiq.demo'

// ?demo=1 turns the strip on and ?demo=0 turns it off. The choice survives in-app navigation,
// whose links drop the query string (architecture: hide demo controls behind ?demo=1).
function useDemoEnabled() {
  const { search } = useLocation()
  const param = new URLSearchParams(search).get('demo')
  try {
    if (param === '1') window.sessionStorage.setItem(DEMO_KEY, '1')
    if (param === '0') window.sessionStorage.removeItem(DEMO_KEY)
    return window.sessionStorage.getItem(DEMO_KEY) === '1'
  } catch {
    return param === '1'
  }
}

const speeds = [1, 60, 600]

export function DemoControls() {
  const enabled = useDemoEnabled()
  const { now, clockMode, speed, dataMode } = useServerClock()
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  if (!enabled) return null

  const run = async (label: string, action: () => Promise<unknown>) => {
    setBusy(true)
    setMessage(null)
    try {
      await action()
      setMessage(`${label}: done`)
    } catch (error) {
      setMessage(`${label} failed: ${error instanceof Error ? error.message : 'unknown error'}`)
    } finally {
      setBusy(false)
      // Re-read clock and mode either way, so the badges match the server.
      requestClockRefresh()
    }
  }

  const changeSpeed = (nextSpeed: number) =>
    run(`Clock ${nextSpeed}x`, () =>
      setClock(
        nextSpeed === 1
          ? { mode: 'system', speed: 1 }
          : {
              mode: 'simulated',
              speed: nextSpeed,
              set_to: new Date(now).toISOString(),
            },
      ),
    )

  // Jumps the simulated clock ahead so missed acknowledgments and escalations show up in the demo.
  const jumpAhead = () =>
    run('Jump 30 min', () =>
      setClock({
        mode: 'simulated',
        speed: clockMode === 'simulated' ? speed : 1,
        set_to: new Date(now + 30 * 60_000).toISOString(),
      }),
    )

  const evaluateAll = () =>
    run('Evaluate all', async () => {
      const { facilities, fromFixture } = await getFacilities()
      if (fromFixture) throw new Error('backend not connected')
      await Promise.allSettled(facilities.map((facility) => evaluateFacility(facility.facility_id)))
    })

  const buttonClass = (active: boolean) =>
    `rounded-md px-3 py-1.5 text-xs font-semibold disabled:opacity-50 ${
      active ? 'bg-amber-400 text-slate-950' : 'bg-slate-700 text-white hover:bg-slate-600'
    }`

  return (
    <>
      {/* Spacer so the fixed strip never covers the bottom of a page. */}
      <div aria-hidden="true" className="h-16" />
      <div
        aria-label="Demo controls"
        className="fixed inset-x-0 bottom-0 z-30 flex flex-wrap items-center gap-3 border-t border-slate-700 bg-slate-900 px-4 py-2 text-white"
        role="toolbar"
      >
        <span className="text-xs font-bold uppercase tracking-wide text-amber-300">Demo</span>

        <div className="flex items-center gap-1">
          <span className="mr-1 text-xs text-slate-300">Data</span>
          {(['live', 'replay'] as const).map((mode) => (
            <button
              className={buttonClass(dataMode === mode)}
              disabled={busy}
              key={mode}
              onClick={() => void run(`Mode ${mode}`, () => setDataMode(mode))}
              type="button"
            >
              {mode.toUpperCase()}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1">
          <span className="mr-1 text-xs text-slate-300">Clock</span>
          {speeds.map((item) => (
            <button
              className={buttonClass(item === 1 ? clockMode === 'system' : clockMode === 'simulated' && speed === item)}
              disabled={busy}
              key={item}
              onClick={() => void changeSpeed(item)}
              type="button"
            >
              {item}x
            </button>
          ))}
          <button className={buttonClass(false)} disabled={busy} onClick={() => void jumpAhead()} type="button">
            +30 min
          </button>
        </div>

        <button className={buttonClass(false)} disabled={busy} onClick={() => void evaluateAll()} type="button">
          Evaluate all facilities
        </button>

        <Link className="text-xs text-slate-300 underline" to="/">
          Watchlist
        </Link>

        {message && <span className="text-xs text-slate-300">{message}</span>}

        <Link className="ml-auto text-xs text-slate-400 underline" to="?demo=0">
          Hide
        </Link>
      </div>
    </>
  )
}
