import { useEffect, useState } from 'react'
import { apiGet } from '../api'
import type { DataMode } from '../types'
import { useEventSource } from './useEventSource'

export type ClockMode = 'system' | 'simulated'

type ClockResponse = { mode: ClockMode; now_sim: string; now_wall: string; speed: number }
type HealthResponse = { ok: boolean; data_mode: DataMode }

// Simulated time keeps moving between server updates: anchor + elapsed wall time * speed.
type ClockAnchor = { mode: ClockMode; simMs: number; wallMs: number; speed: number }

const systemAnchor = (): ClockAnchor => ({ mode: 'system', simMs: Date.now(), wallMs: Date.now(), speed: 1 })

function anchorFrom(clock: Pick<ClockResponse, 'mode' | 'now_sim' | 'speed'>): ClockAnchor {
  return { mode: clock.mode, simMs: new Date(clock.now_sim).getTime(), wallMs: Date.now(), speed: clock.speed }
}

function simNow(anchor: ClockAnchor) {
  return anchor.simMs + (Date.now() - anchor.wallMs) * anchor.speed
}

export const CLOCK_REFRESH_EVENT = 'closureiq:clock-refresh'

export function requestClockRefresh() {
  window.dispatchEvent(new Event(CLOCK_REFRESH_EVENT))
}

// loading: no answer from /api/clock yet; unavailable: the request failed, so `now` is not the server clock.
export type ClockStatus = 'loading' | 'ok' | 'unavailable'

// Deadlines and escalation run on the simulated clock (architecture: "Two clocks").
// DEPRECATED(closureiq): the hook no longer silently falls back to browser time; it reports clockStatus instead.
// // Falls back to the browser clock when the API is not running.
export function useServerClock() {
  const [anchor, setAnchor] = useState<ClockAnchor>(systemAnchor)
  const [clockStatus, setClockStatus] = useState<ClockStatus>('loading')
  const [now, setNow] = useState(Date.now)
  const [dataMode, setDataMode] = useState<DataMode | null>(null)
  const { subscribe } = useEventSource()

  const applyClock = (clock: Pick<ClockResponse, 'mode' | 'now_sim' | 'speed'>) => {
    const nextAnchor = anchorFrom(clock)
    setAnchor(nextAnchor)
    setNow(simNow(nextAnchor))
    setClockStatus('ok')
  }

  useEffect(() => {
    const refresh = () => {
      apiGet<ClockResponse>('/clock')
        .then(applyClock)
        // DEPRECATED(closureiq): replaced by an explicit clockStatus shown on screen.
        // .catch(() => console.warn('Clock API unavailable; using browser time'))
        .catch(() => setClockStatus('unavailable'))
      apiGet<HealthResponse>('/health')
        .then((health) => setDataMode(health.data_mode))
        .catch(() => console.warn('Health API unavailable'))
    }
    refresh()
    // Demo controls fire this after changing the clock or mode, so every screen re-reads them even if
    // the backend's clock.changed event does not arrive.
    window.addEventListener(CLOCK_REFRESH_EVENT, refresh)
    return () => window.removeEventListener(CLOCK_REFRESH_EVENT, refresh)
  }, [])

  useEffect(() => {
    const unsubscribeClock = subscribe('clock.changed', (event) => {
      try {
        applyClock(JSON.parse(event.data))
      } catch (error) {
        console.warn('Unable to parse clock.changed event', error)
      }
    })
    const unsubscribeMode = subscribe('mode.changed', (event) => {
      try {
        setDataMode((JSON.parse(event.data) as { data_mode: DataMode }).data_mode)
      } catch (error) {
        console.warn('Unable to parse mode.changed event', error)
      }
    })
    return () => {
      unsubscribeClock()
      unsubscribeMode()
    }
  }, [subscribe])

  useEffect(() => {
    const intervalId = window.setInterval(() => setNow(simNow(anchor)), 1_000)
    return () => window.clearInterval(intervalId)
  }, [anchor])

  return {
    now,
    clockStatus,
    clockMode: anchor.mode,
    speed: anchor.speed,
    dataMode,
  }
}
