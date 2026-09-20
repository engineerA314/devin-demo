export type EmbedConfig = {
  mode: 'embedded' | 'unconfigured'
  dashboardId?: string
  supersetDomain?: string
}

export type OperationsOverview = {
  configured: {
    devin: boolean
    repository: string
    repositories?: string[]
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
    totalIncidentEvents: number
    duplicateEventDeliveries: number
    activeRuns: number
    successfulRuns: number
    failedRuns: number
    approvalPending: number
    medianTimeToIssueSeconds?: number
    medianTimeToPrSeconds?: number
    pendingAgentWork: number
    dispatchFailureRate: number
    ciPassRate?: number | null
    ciFeedbackRetries: number
  }
  health: Array<{
    name: string
    status: 'healthy' | 'degraded'
    detail: string
  }>
  runs: ResolutionRun[]
  incidents: Array<Record<string, unknown>>
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
  upstreamIncidentId?: string
  incidentStatus: 'triggered' | 'acknowledged' | 'resolved'
  eventCount: number
  duplicateEventCount: number
  latestEventAt: string
  title: string
  service: string
  severity: string
  status: 'active' | 'complete' | 'failed'
  stage: 'alert' | 'attribution' | 'issue' | 'pull_request' | 'resolved'
  currentActivity: string
  owner: string
  outcome:
    | 'alert_received'
    | 'attributing'
    | 'issue_authoring'
    | 'attribution_review'
    | 'non_code'
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
  observability?: {
    id: string
    provider: string
    mode: string
    capturedAt: string
    window: { start: string; end: string }
    description: string
    status: 'available' | 'reviewed'
    artifacts: Array<{
      id: string
      label: string
      source: string
      record_count: number
      sample_count: number
      summary: string
    }>
  } | null
  durations: {
    toAttributionSeconds?: number
    toIssueSeconds?: number
    toPrSeconds?: number
    toVerificationSeconds?: number
  }
  verification: {
    testsPassed?: string
    buildPassed: boolean
    source?: string
  }
  ci: {
    status: 'not_configured' | 'pending' | 'failed' | 'passed'
    headSha?: string
    checkedAt?: string
    failedChecks: Array<{
      name: string
      status: string
      conclusion?: string
      url?: string
      completedAt?: string
    }>
    feedbackAttempts: number
    maxFeedbackAttempts: number
    feedbackError?: string
    retryExhausted: boolean
  }
  attribution: {
    status: 'pending' | 'approved' | 'human_review' | 'non_code'
    completedAt?: string
    disposition?: 'code_change_required' | 'non_code' | 'insufficient_evidence'
    confidence?: number
    primary_component?: string
    primary_repository?: string
    related_components?: Array<{
      component: string
      repository?: string
      reason: string
    }>
    evidence?: string[]
    counter_evidence?: string[]
    suspected_paths?: string[]
    reproduction?: {
      status: 'reproduced' | 'falsified' | 'not_run' | 'inconclusive'
      method: string
      command?: string | null
      result: string
    }
    summary?: string
    policy_status?: string
    policy_reason?: string
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
    kind: 'alert' | 'evidence' | 'attribution' | 'agent' | 'issue' | 'code' | 'pull_request' | 'verified'
    label: string
    occurredAt: string
    elapsedSeconds?: number
    url?: string
  }>
  triageSession?: SessionArtifact
  issueSession?: SessionArtifact
  remediationSession?: SessionArtifact
  issue?: IssueArtifact
  pullRequest?: PullRequestArtifact
  dispatch: {
    triage: string
    issue: string
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
  incident_id: string
  event_action: 'trigger' | 'update' | 'acknowledge' | 'resolve'
  source: string
  repository?: string
  title: string
  service: string
  severity?: 'SEV-0' | 'SEV-1' | 'SEV-2' | 'SEV-3' | 'SEV-4'
  occurred_at: string
  signals: AlertSignal[]
  evidence: Record<string, unknown>
  metadata: Record<string, unknown>
}

export type AlertAccepted = {
  id: string
  incident_id: string
  status: string
  incident_status: string
  event_count: number
  duplicate_event_count: number
  incident_created: boolean
  event_duplicate: boolean
  duplicate: boolean
  session_id?: string
  session_url?: string
}

export type SetupStatus = {
  liveDispatchReady: boolean
  repository: string
  repositories?: string[]
  dispatchMode: string
  issueIntakeMode: string
  pollIntervalSeconds: number
  checks: Array<{
    key: string
    status: 'ready' | 'missing' | 'optional'
    label: string
    detail: string
    required: boolean
  }>
  requiredActions: string[]
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

export function getSetupStatus(): Promise<SetupStatus> {
  return request<SetupStatus>('/api/v1/setup/status')
}

export function triggerDemoIncident(): Promise<{ id: string; status: string }> {
  return request<{ id: string; status: string }>('/api/incidents/demo', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
}

export function sendIncidentEvent(payload: AlertPayload): Promise<AlertAccepted> {
  return request<AlertAccepted>('/api/v1/incidents/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
