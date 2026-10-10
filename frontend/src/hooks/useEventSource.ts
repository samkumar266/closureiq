import { useCallback, useEffect } from 'react'

export const eventNames = [
  'evaluation.created',
  'approval.recorded',
  'delivery.updated',
  'escalation.fired',
  'clock.changed',
  'mode.changed',
  'source.degraded',
] as const

export type EventName = (typeof eventNames)[number]
export type EventHandler = (event: MessageEvent) => void

const subscribers = new Map<EventName, Set<EventHandler>>(
  eventNames.map((eventName) => [eventName, new Set<EventHandler>()]),
)
const reconnectHandlers = new Set<() => void>()

let eventSource: EventSource | null = null
let hookUsers = 0
let hasConnectedBefore = false

function openEventSource() {
  if (eventSource) {
    return
  }

  eventSource = new EventSource('/api/events')
  eventSource.onopen = () => {
    if (hasConnectedBefore) {
      reconnectHandlers.forEach((handler) => handler())
    }
    hasConnectedBefore = true
  }

  for (const eventName of eventNames) {
    eventSource.addEventListener(eventName, (event) => {
      for (const handler of subscribers.get(eventName) ?? []) {
        handler(event as MessageEvent)
      }
    })
  }
}

function closeEventSource() {
  eventSource?.close()
  eventSource = null
  hasConnectedBefore = false
}

export function useEventSource() {
  useEffect(() => {
    hookUsers += 1
    openEventSource()

    return () => {
      hookUsers -= 1
      if (hookUsers === 0) {
        closeEventSource()
      }
    }
  }, [])

  const subscribe = useCallback(
    (eventName: EventName, handler: EventHandler) => {
      const handlers = subscribers.get(eventName)
      handlers?.add(handler)

      return () => {
        handlers?.delete(handler)
      }
    },
    [],
  )

  const onReconnect = useCallback((handler: () => void) => {
    reconnectHandlers.add(handler)
    return () => {
      reconnectHandlers.delete(handler)
    }
  }, [])

  return { subscribe, onReconnect }
}
