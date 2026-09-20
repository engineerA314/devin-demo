import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  CircleDot,
  Clock3,
  ExternalLink,
  GitPullRequest,
  RefreshCw,
  ShieldCheck,
  Webhook,
  Zap,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import {
  getOperationsOverview,
  triggerDemoIncident,
  type OperationsOverview,
} from '../api'

const refreshIntervalMs = 5_000

export function OperationsDashboard() {
  const [overview, setOverview] = useState<OperationsOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [triggering, setTriggering] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const next = await getOperationsOverview()
      setOverview(next)
      setError(next.warnings[0] ?? null)
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : 'Unable to refresh')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // The dashboard is a live read model; fetch immediately, then poll Devin.
    // oxlint-disable-next-line react/set-state-in-effect
    void refresh()
    const timer = window.setInterval(() => void refresh(), refreshIntervalMs)
    return () => window.clearInterval(timer)
  }, [refresh])

  async function triggerIncident() {
    setTriggering(true)
    setError(null)
    try {
      const incident = await triggerDemoIncident()
      if (incident.status === 'trigger_failed') {
        throw new Error('Devin rejected the incident webhook. Check the automation.')
      }
      await refresh()
    } catch (triggerError) {
      setError(
        triggerError instanceof Error ? triggerError.message : 'Unable to trigger incident',
      )
    } finally {
      setTriggering(false)
    }
  }

  const metrics = overview?.metrics
  const isReady = overview?.configured.devin && overview.configured.triageWebhook
  const pullRequests = Array.from(
    new Map(
      (overview?.sessions ?? [])
        .flatMap(session => session.pullRequests)
        .filter(pullRequest => pullRequest.pr_url)
        .map(pullRequest => [pullRequest.pr_url, pullRequest]),
    ).values(),
  )

  return (
    <div className="ops-page">
      <section className="ops-hero">
        <div>
          <div className="ops-hero__eyebrow">
            <ShieldCheck size={14} /> Incident Autopilot
          </div>
          <h1>Production recovery, coordinated by Devin</h1>
          <p>
            Alerts become reproducible issues. Validated issues become tested pull
            requests, with a human approval gate before merge.
          </p>
        </div>
        <button
          className="incident-button"
          disabled={!isReady || triggering}
          onClick={() => void triggerIncident()}
          type="button"
        >
          {triggering ? <RefreshCw className="spin" size={17} /> : <Zap size={17} />}
          {triggering ? 'Dispatching alert' : 'Simulate production incident'}
        </button>
      </section>

      <div className={`control-status ${isReady ? 'control-status--ready' : ''}`}>
        <span className="control-status__dot" />
        <strong>{isReady ? 'Automation online' : 'Setup required'}</strong>
        <span>
          {overview?.configured.repository ?? 'engineerA314/superset'} · polling every 5s
        </span>
        <button onClick={() => void refresh()} type="button" aria-label="Refresh status">
          <RefreshCw size={14} />
        </button>
      </div>

      {error && <div className="ops-error">{error}</div>}

      <section className="ops-metrics" aria-label="Automation metrics">
        <Metric label="Incidents" value={metrics?.incidents ?? 0} icon={AlertTriangle} />
        <Metric label="Active Devins" value={metrics?.activeSessions ?? 0} icon={Bot} />
        <Metric label="Pull requests" value={metrics?.pullRequests ?? 0} icon={GitPullRequest} />
        <Metric
          label="Success rate"
          value={`${metrics?.successRate ?? 0}%`}
          icon={CheckCircle2}
        />
        <Metric
          label="Completed Devins"
          value={metrics?.completedSessions ?? 0}
          icon={Activity}
        />
      </section>

      <section className="automation-flow" aria-labelledby="automation-flow-title">
        <div className="section-heading">
          <div>
            <span>Native Devin workflow</span>
            <h2 id="automation-flow-title">Two agents, one reviewable handoff</h2>
          </div>
          <span className="live-badge"><CircleDot size={12} /> Live</span>
        </div>
        <div className="flow-grid">
          <FlowStep
            number="01"
            title="Alert received"
            description="A Datadog-compatible webhook carries the incident signal and evidence."
            icon={Webhook}
            state={overview?.incidents.length ? 'complete' : 'waiting'}
          />
          <FlowStep
            number="02"
            title="Triage Devin"
            description="Reproduces or falsifies the alert, then creates a scoped GitHub issue."
            icon={Bot}
            state={sessionState(overview, 'incident-triage')}
          />
          <FlowStep
            number="03"
            title="Issue contract"
            description="The devin-ready label dispatches a fresh remediation session."
            icon={CircleDot}
            state={overview?.issues.length ? 'complete' : 'waiting'}
          />
          <FlowStep
            number="04"
            title="Fix and verify"
            description="A regression test, focused fix, CI evidence, and linked PR await approval."
            icon={GitPullRequest}
            state={sessionState(overview, 'incident-remediation')}
          />
        </div>
      </section>

      <div className="ops-grid">
        <section className="ops-panel ops-panel--wide">
          <div className="section-heading section-heading--compact">
            <div>
              <span>Response timeline</span>
              <h2>Incidents</h2>
            </div>
          </div>
          {loading ? (
            <EmptyState copy="Loading incident history…" />
          ) : overview?.incidents.length ? (
            <div className="incident-list">
              {overview.incidents.map(incident => (
                <article className="incident-row" key={incident.id}>
                  <span className="severity-badge">{incident.severity}</span>
                  <div className="incident-row__main">
                    <strong>{incident.title}</strong>
                    <span>
                      {incident.id} · {incident.service} · {formatDate(incident.detected_at)}
                    </span>
                  </div>
                  <div className="incident-row__signal">
                    <strong>{incident.error_rate}%</strong>
                    <span>error rate</span>
                  </div>
                  <StatusBadge status={incident.status} />
                </article>
              ))}
            </div>
          ) : (
            <EmptyState copy="No incidents dispatched yet." />
          )}
        </section>

        <section className="ops-panel">
          <div className="section-heading section-heading--compact">
            <div>
              <span>Cloud workers</span>
              <h2>Devin sessions</h2>
            </div>
          </div>
          {overview?.sessions.length ? (
            <div className="resource-list">
              {overview.sessions.map(session => (
                <a
                  className="resource-row"
                  href={session.url}
                  key={session.id}
                  rel="noreferrer"
                  target="_blank"
                >
                  <span className="resource-row__icon"><Bot size={16} /></span>
                  <span>
                    <strong>{session.title || session.id}</strong>
                    <small>
                      {session.statusDetail || session.status}
                      {session.acusConsumed > 0 ? ` · ${session.acusConsumed} ACU` : ''}
                    </small>
                  </span>
                  <ExternalLink size={14} />
                </a>
              ))}
            </div>
          ) : (
            <EmptyState copy="Sessions appear here when the webhook fires." />
          )}
        </section>

        <section className="ops-panel">
          <div className="section-heading section-heading--compact">
            <div>
              <span>Engineering artifacts</span>
              <h2>Issues and pull requests</h2>
            </div>
          </div>
          {overview?.issues.length || pullRequests.length ? (
            <div className="resource-list">
              {(overview?.issues ?? []).map(issue => (
                <a
                  className="resource-row"
                  href={issue.url}
                  key={issue.number}
                  rel="noreferrer"
                  target="_blank"
                >
                  <span className="resource-row__icon"><CircleDot size={16} /></span>
                  <span>
                    <strong>#{issue.number} {issue.title}</strong>
                    <small>{issue.state} · {issue.labels.join(', ')}</small>
                  </span>
                  <ExternalLink size={14} />
                </a>
              ))}
              {pullRequests.map(pullRequest => (
                <a
                  className="resource-row"
                  href={pullRequest.pr_url}
                  key={pullRequest.pr_url}
                  rel="noreferrer"
                  target="_blank"
                >
                  <span className="resource-row__icon"><GitPullRequest size={16} /></span>
                  <span>
                    <strong>Remediation pull request</strong>
                    <small>{pullRequest.pr_state || 'open'} · ready for review</small>
                  </span>
                  <ExternalLink size={14} />
                </a>
              ))}
            </div>
          ) : (
            <EmptyState copy="Validated issues and remediation PRs appear here." />
          )}
        </section>
      </div>
    </div>
  )
}

function Metric({
  label,
  value,
  icon: Icon,
}: {
  label: string
  value: number | string
  icon: typeof Activity
}) {
  return (
    <article className="ops-metric">
      <span className="ops-metric__icon"><Icon size={16} /></span>
      <div><span>{label}</span><strong>{value}</strong></div>
    </article>
  )
}

function FlowStep({
  number,
  title,
  description,
  icon: Icon,
  state,
}: {
  number: string
  title: string
  description: string
  icon: typeof Activity
  state: 'waiting' | 'active' | 'complete' | 'failed'
}) {
  return (
    <article className={`flow-step flow-step--${state}`}>
      <div className="flow-step__top"><span>{number}</span><Icon size={18} /></div>
      <strong>{title}</strong>
      <p>{description}</p>
      <StatusBadge status={state} />
    </article>
  )
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`stage-badge stage-badge--${status}`}>{humanize(status)}</span>
}

function EmptyState({ copy }: { copy: string }) {
  return <div className="empty-state"><Clock3 size={17} /><span>{copy}</span></div>
}

function sessionState(
  overview: OperationsOverview | null,
  tag: string,
): 'waiting' | 'active' | 'complete' | 'failed' {
  const session = overview?.sessions.find(item => item.tags.includes(tag))
  if (!session) return 'waiting'
  if (session.status === 'error') return 'failed'
  if (
    session.status === 'exit' ||
    session.statusDetail === 'waiting_for_user' ||
    session.statusDetail === 'finished'
  ) return 'complete'
  return 'active'
}

function humanize(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase())
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('en', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}
