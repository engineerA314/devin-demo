export type EmbedConfig = {
  mode: 'embedded' | 'preview'
  dashboardId?: string
  supersetDomain?: string
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init)
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `Request failed with status ${response.status}`)
  }
  return response.json() as Promise<T>
}

export function getEmbedConfig(): Promise<EmbedConfig> {
  return request<EmbedConfig>('/api/config')
}

export async function fetchGuestToken(): Promise<string> {
  const result = await request<{ token: string }>('/api/superset/guest-token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  return result.token
}
