// DEPRECATED(closureiq): sample-data fallbacks removed; API failures now surface as errors on screen.
// import { loadFacilities, loadRecommendation, loadRoster, sourcesFromRecommendation } from './fixtures'
import type { Posture } from './theme'
import type {
  ApprovalResponse,
  // DEPRECATED(closureiq): only used by normalizeFacility below.
  // ConfidenceLevel,
  DataMode,
  DecisionRecord,
  Delivery,
  Employee,
  // DEPRECATED(closureiq): Facility list items are no longer fetched (single-facility app).
  // Facility,
  FacilityProfile,
  FacilityStatus,
  NotificationPackage,
  Recommendation,
  ReplayResult,
} from './types'

// Error shape from docs/contract.md: { error: { code, message, detail } }
export class ApiError extends Error {
  status: number
  code: string
  detail: Record<string, unknown>
  // Full response body. 409 already_decided carries the existing approval next to the error.
  body: unknown

  constructor(status: number, code: string, message: string, detail: Record<string, unknown> = {}, body: unknown = null) {
    super(message)
    this.status = status
    this.code = code
    this.detail = detail
    this.body = body
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError(0, 'network_error', 'API is unreachable')
  }

  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const error = (body as { error?: { code?: string; message?: string; detail?: Record<string, unknown> } } | null)
      ?.error
    throw new ApiError(
      response.status,
      error?.code ?? 'http_error',
      error?.message ?? `Request failed with status ${response.status}`,
      error?.detail ?? {},
      body,
    )
  }
  return body as T
}

export function apiGet<T>(path: string) {
  return request<T>(path)
}

export function apiPost<T>(path: string, body: unknown = {}) {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) })
}

// DEPRECATED(closureiq) START: facility list (Watchlist) and sample-data fallbacks. The app now opens on one
// facility and shows API failures instead of silently substituting fixtures.
// // The backend currently sends current.confidence as { level, reasons }; the contract says a plain level.
// function normalizeFacility(facility: Facility): Facility {
//   if (!facility.current) return facility
//   const confidence = facility.current.confidence as unknown
//   const level =
//     confidence && typeof confidence === 'object' && 'level' in confidence
//       ? (confidence as { level: string }).level
//       : confidence
//   return { ...facility, current: { ...facility.current, confidence: level as ConfidenceLevel } }
// }
//
// // Falls back to the committed fixtures while the backend is not running.
// export async function getFacilities(): Promise<{ facilities: Facility[]; fromFixture: boolean }> {
//   try {
//     const { facilities } = await apiGet<{ facilities: Facility[] }>('/facilities')
//     return { facilities: facilities.map(normalizeFacility), fromFixture: false }
//   } catch (error) {
//     console.warn('Using facilities fixture:', error)
//     return { facilities: loadFacilities(), fromFixture: true }
//   }
// }
//
// // status.evaluation is null until the backend has run its first evaluation for the facility.
// export type FacilityStatusResult = Omit<FacilityStatus, 'evaluation'> & { evaluation: Recommendation | null }
//
// export async function getFacilityStatus(
//   facilityId: string,
// ): Promise<{ status: FacilityStatusResult | null; fromFixture: boolean }> {
//   try {
//     const status = await apiGet<FacilityStatusResult>(`/facilities/${facilityId}/status`)
//     return { status, fromFixture: false }
//   } catch (error) {
//     if (error instanceof ApiError && error.status === 404) {
//       return { status: null, fromFixture: false }
//     }
//     console.warn('Using recommendation fixture:', error)
//     const evaluation = loadRecommendation(facilityId)
//     if (!evaluation) {
//       return { status: null, fromFixture: true }
//     }
//     return {
//       status: {
//         facility_id: facilityId,
//         evaluation,
//         approval: null,
//         notification_id: null,
//         sources: sourcesFromRecommendation(evaluation),
//       },
//       fromFixture: true,
//     }
//   }
// }
//
// export async function getRoster(facilityId: string): Promise<Employee[]> {
//   try {
//     const { employees } = await apiGet<{ employees: Employee[] }>(`/facilities/${facilityId}/roster`)
//     return employees
//   } catch (error) {
//     console.warn('Using roster fixture:', error)
//     return loadRoster(facilityId)
//   }
// }
// DEPRECATED(closureiq) END

// GET /api/facilities/{id}: name, location (with timezone), hours and windows.
export function getFacilityProfile(facilityId: string) {
  return apiGet<FacilityProfile>(`/facilities/${facilityId}`)
}

// status.evaluation is null until the backend has run its first evaluation for the facility.
export type FacilityStatusResult = Omit<FacilityStatus, 'evaluation'> & { evaluation: Recommendation | null }

export function getFacilityStatus(facilityId: string) {
  return apiGet<FacilityStatusResult>(`/facilities/${facilityId}/status`)
}

export async function getRoster(facilityId: string): Promise<Employee[]> {
  const { employees } = await apiGet<{ employees: Employee[] }>(`/facilities/${facilityId}/roster`)
  return employees
}

// DEPRECATED(closureiq) START: no screen triggers evaluation any more; the backend evaluates after every poll.
// export function evaluateFacility(facilityId: string) {
//   return apiPost<Recommendation>(`/facilities/${facilityId}/evaluate`)
// }
// DEPRECATED(closureiq) END

export function getPackagePreview(evaluationId: string, posture?: Posture) {
  const query = posture ? `?posture=${posture}` : ''
  return apiGet<NotificationPackage>(`/evaluations/${evaluationId}/package-preview${query}`)
}

export function approveEvaluation(evaluationId: string, actor: string) {
  return apiPost<ApprovalResponse>(`/evaluations/${evaluationId}/approve`, { actor })
}

export function rejectEvaluation(evaluationId: string, actor: string, reason: string) {
  return apiPost<ApprovalResponse>(`/evaluations/${evaluationId}/reject`, { actor, reason })
}

export function overrideEvaluation(evaluationId: string, actor: string, posture: Posture, reason: string) {
  return apiPost<ApprovalResponse>(`/evaluations/${evaluationId}/override`, { actor, posture, reason })
}

export function getNotification(notificationId: string) {
  return apiGet<NotificationPackage>(`/notifications/${notificationId}`)
}

export function acknowledgeDelivery(deliveryId: string) {
  return apiPost<Delivery>(`/deliveries/${deliveryId}/ack`)
}

export function getEvaluation(evaluationId: string) {
  return apiGet<Recommendation>(`/evaluations/${evaluationId}`)
}

export function getRecord(evaluationId: string) {
  return apiGet<DecisionRecord>(`/evaluations/${evaluationId}/record`)
}

export function replayEvaluation(evaluationId: string) {
  return apiPost<ReplayResult>(`/evaluations/${evaluationId}/replay`)
}

export function setDataMode(dataMode: DataMode) {
  return apiPost<{ data_mode: DataMode }>('/mode', { data_mode: dataMode })
}

export type ClockSettings = { mode: 'system' | 'simulated'; speed: number; set_to?: string | null }

export function setClock(settings: ClockSettings) {
  return apiPost<{ mode: string; now_sim: string; now_wall: string; speed: number }>('/clock', settings)
}

export type ChatEvent =
  | { event: 'tool'; data: { name: string; args: Record<string, unknown> } }
  | { event: 'token'; data: { text: string } }
  | { event: 'replaced'; data: { text: string } }
  | { event: 'done'; data: { evaluation_id: string; validated: boolean; whatif_id: string | null } }

// POST /api/agent/chat answers with server-sent events. EventSource cannot POST, so read the stream by hand.
export async function streamChat(
  body: { facility_id: string; evaluation_id: string; message: string },
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
) {
  let response: Response
  try {
    response = await fetch('/api/agent/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(body),
      signal,
    })
  } catch {
    throw new ApiError(0, 'network_error', 'API is unreachable')
  }
  if (!response.ok || !response.body) {
    const errorBody: unknown = await response.json().catch(() => null)
    const error = (errorBody as { error?: { code?: string; message?: string } } | null)?.error
    throw new ApiError(response.status, error?.code ?? 'http_error', error?.message ?? 'Chat failed', {}, errorBody)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split(/\r?\n\r?\n/)
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      let eventName = 'message'
      const dataLines: string[] = []
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith('event:')) eventName = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
      }
      if (dataLines.length === 0) continue
      try {
        onEvent({ event: eventName, data: JSON.parse(dataLines.join('\n')) } as ChatEvent)
      } catch {
        console.warn('Ignoring malformed chat event', frame)
      }
    }
  }
}
