import { loadFacilities, loadRecommendation, loadRoster, sourcesFromRecommendation } from './fixtures'
import type { ConfidenceLevel, Employee, Facility, FacilityStatus, Recommendation } from './types'

// Error shape from docs/contract.md: { error: { code, message, detail } }
export class ApiError extends Error {
  status: number
  code: string
  detail: Record<string, unknown>

  constructor(status: number, code: string, message: string, detail: Record<string, unknown> = {}) {
    super(message)
    this.status = status
    this.code = code
    this.detail = detail
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

// The backend currently sends current.confidence as { level, reasons }; the contract says a plain level.
function normalizeFacility(facility: Facility): Facility {
  if (!facility.current) return facility
  const confidence = facility.current.confidence as unknown
  const level =
    confidence && typeof confidence === 'object' && 'level' in confidence
      ? (confidence as { level: string }).level
      : confidence
  return { ...facility, current: { ...facility.current, confidence: level as ConfidenceLevel } }
}

// Falls back to the committed fixtures while the backend is not running.
export async function getFacilities(): Promise<{ facilities: Facility[]; fromFixture: boolean }> {
  try {
    const { facilities } = await apiGet<{ facilities: Facility[] }>('/facilities')
    return { facilities: facilities.map(normalizeFacility), fromFixture: false }
  } catch (error) {
    console.warn('Using facilities fixture:', error)
    return { facilities: loadFacilities(), fromFixture: true }
  }
}

// status.evaluation is null until the backend has run its first evaluation for the facility.
export type FacilityStatusResult = Omit<FacilityStatus, 'evaluation'> & { evaluation: Recommendation | null }

export async function getFacilityStatus(
  facilityId: string,
): Promise<{ status: FacilityStatusResult | null; fromFixture: boolean }> {
  try {
    const status = await apiGet<FacilityStatusResult>(`/facilities/${facilityId}/status`)
    return { status, fromFixture: false }
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return { status: null, fromFixture: false }
    }
    console.warn('Using recommendation fixture:', error)
    const evaluation = loadRecommendation(facilityId)
    if (!evaluation) {
      return { status: null, fromFixture: true }
    }
    return {
      status: {
        facility_id: facilityId,
        evaluation,
        approval: null,
        notification_id: null,
        sources: sourcesFromRecommendation(evaluation),
      },
      fromFixture: true,
    }
  }
}

export async function getRoster(facilityId: string): Promise<Employee[]> {
  try {
    const { employees } = await apiGet<{ employees: Employee[] }>(`/facilities/${facilityId}/roster`)
    return employees
  } catch (error) {
    console.warn('Using roster fixture:', error)
    return loadRoster(facilityId)
  }
}

export function evaluateFacility(facilityId: string) {
  return apiPost<Recommendation>(`/facilities/${facilityId}/evaluate`)
}
