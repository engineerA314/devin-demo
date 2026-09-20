export type EmbedConfig = {
  mode: 'embedded' | 'preview'
  dashboardId?: string
  supersetDomain?: string
}

export type OperationsOverview = {
  configured: {
    devin: boolean
    triageWebhook: boolean
    repository: string
    dispatchMode: string
    managedIssueLabel: string
  }
  metrics: {
    incidents: number
    activeSessions: number
    completedSessions: number
    failedSessions: number
    pullRequests: number
    acusConsumed: number
    successRate: number
  }
  summary: {
    totalRuns: number
    activeRuns: number
    successfulRuns: number
    failedRuns: number
    approvalPending: number
    medianTimeToIssueSeconds?: number
    medianTimeToPrSeconds?: number
  }
  health: Array<{
    name: string
    status: 'healthy' | 'degraded'
    detail: string
  }>
  runs: ResolutionRun[]
  incidents: Array<Record<string, unknown>>
  automations: Array<{
    id: string
    name: string
    enabled: boolean
    lastInvocation: unknown
  }>
  sessions: Array<{
    id: string
    title: string
    status: string
    statusDetail?: string
    url: string
    tags: string[]
    acusConsumed: number
    pullRequests: Array<{ pr_url: string; pr_state: string }>
    createdAt: number
    updatedAt: number
    automationId?: string
  }>
  issues: Array<{
    number: number
    title: string
    state: string
    url: string
    labels: string[]
    createdAt: string
  }>
  pullRequests: Array<PullRequestArtifact>
  generatedAt: string
  warnings: string[]
}

export type SessionArtifact = {
  id: string
  title?: string
  status: string
  statusDetail?: string
  url: string
  tags: string[]
  acusConsumed: number
  pullRequests: Array<{ pr_url: string; pr_state: string }>
  createdAt: number
  updatedAt: number
  automationId?: string
}

export type IssueArtifact = {
  number: number
  title: string
  state: string
  url: string
  labels: string[]
  createdAt: string
}

export type PullRequestArtifact = {
  number: number
  title: string
  state: string
  url: string
  createdAt: string
  mergedAt?: string
}

export type ResolutionRun = {
  id: string
  sourceType: 'alert' | 'issue'
  sourceName: string
  repository: string
  externalEventId: string
  title: string
  service: string
  severity: string
  status: 'active' | 'complete' | 'failed'
  stage: 'alert' | 'issue' | 'pull_request' | 'resolved'
  currentActivity: string
  owner: string
  outcome:
    | 'alert_received'
    | 'triaging'
    | 'issue_created'
    | 'remediating'
    | 'pr_opened'
    | 'ready_for_review'
    | 'merged'
    | 'failed'
  detectedAt: string
  completedAt?: string
  elapsedSeconds?: number
  humanAction: string
  signals: AlertSignal[]
  durations: {
    toIssueSeconds?: number
    toPrSeconds?: number
    toVerificationSeconds?: number
  }
  verification: {
    testsPassed?: string
    buildPassed: boolean
    source?: string
  }
  report: {
    title: string
    summary: string
    sections: Array<{
      key: string
      title: string
      body: string
      source: string
      url?: string
    }>
    sources: Array<{
      label: string
      kind: 'triage' | 'remediation'
      url: string
    }>
  }
  milestones: Array<{
    kind: 'alert' | 'agent' | 'issue' | 'code' | 'pull_request' | 'verified'
    label: string
    occurredAt: string
    elapsedSeconds?: number
    url?: string
  }>
  triageSession?: SessionArtifact
  remediationSession?: SessionArtifact
  issue?: IssueArtifact
  pullRequest?: PullRequestArtifact
  dispatch: {
    triage: string
    remediation: string
  }
  errorDetail?: string
}

export type AlertSignal = {
  key: string
  label: string
  value: string | number
  unit?: string | null
}

export type AlertPayload = {
  event_id: string
  source: string
  repository?: string
  title: string
  service: string
  severity: 'SEV-0' | 'SEV-1' | 'SEV-2' | 'SEV-3' | 'SEV-4'
  occurred_at: string
  signals: AlertSignal[]
  evidence: Record<string, unknown>
  metadata: Record<string, unknown>
}

export type AlertAccepted = {
  id: string
  status: string
  duplicate: boolean
  session_id?: string
  session_url?: string
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

export function getOperationsOverview(): Promise<OperationsOverview> {
  return request<OperationsOverview>('/api/operations/overview')
}

export function triggerDemoIncident(): Promise<{ id: string; status: string }> {
  return request<{ id: string; status: string }>('/api/incidents/demo', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
}

export function triggerAlert(payload: AlertPayload): Promise<AlertAccepted> {
  return request<AlertAccepted>('/api/v1/alerts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
