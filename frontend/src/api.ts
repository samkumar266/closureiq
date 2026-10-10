import { loadFacilities } from './fixtures'
import type { Facility } from './types'

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

// Falls back to the committed fixtures while the backend is not running.
export async function getFacilities(): Promise<{ facilities: Facility[]; fromFixture: boolean }> {
  try {
    const { facilities } = await apiGet<{ facilities: Facility[] }>('/facilities')
    return { facilities, fromFixture: false }
  } catch (error) {
    console.warn('Using facilities fixture:', error)
    return { facilities: loadFacilities(), fromFixture: true }
  }
}
