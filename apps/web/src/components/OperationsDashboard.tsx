import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Bot,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Clock3,
  ExternalLink,
  FileCheck2,
  FileText,
  GitPullRequest,
  ListFilter,
  Radio,
  RefreshCw,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  UserRoundCheck,
  Users,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getOperationsOverview,
  type OperationsOverview,
  type ResolutionRun,
} from '../api'

const refreshIntervalMs = 5_000

type RunFilter = 'all' | 'active' | 'review' | 'failed'
type WorkflowStage = ResolutionRun['stage']

const columns: Array<{
  id: WorkflowStage
  label: string
  description: string
}> = [
  { id: 'alert', label: 'Alert', description: 'Detection & triage' },
  { id: 'issue', label: 'Validated issue', description: 'Reproduced & scoped' },
  { id: 'pull_request', label: 'Pull request', description: 'Fix, test & review' },
  { id: 'resolved', label: 'Resolved', description: 'Merged remediation' },
]

export function OperationsDashboard() {
  const [overview, setOverview] = useState<OperationsOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<RunFilter>('all')
  const [selectedRunId, setSelectedRunId] = useState(runIdFromHash)

  const refresh = useCallback(async () => {
    try {
      const next = await getOperationsOverview()
      setOverview(next)
      setError(next.warnings.length ? next.warnings.join(' · ') : null)
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : 'Unable to refresh')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect
    void refresh()
    const timer = window.setInterval(() => void refresh(), refreshIntervalMs)
    return () => window.clearInterval(timer)
  }, [refresh])

  useEffect(() => {
    const syncSelection = () => setSelectedRunId(runIdFromHash())
    window.addEventListener('hashchange', syncSelection)
    window.addEventListener('popstate', syncSelection)
    return () => {
      window.removeEventListener('hashchange', syncSelection)
      window.removeEventListener('popstate', syncSelection)
    }
  }, [])

  const runs = useMemo(() => overview?.runs ?? [], [overview])
  const selectedRun = runs.find(run => run.id === selectedRunId)
  const filteredRuns = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return runs.filter(run => {
      const matchesQuery = !normalizedQuery || [run.id, run.title, run.service, run.issue?.title]
        .filter(Boolean)
        .some(value => value?.toLowerCase().includes(normalizedQuery))
      const matchesFilter = filter === 'all'
        || (filter === 'active' && run.status === 'active')
        || (filter === 'review' && run.outcome === 'ready_for_review')
        || (filter === 'failed' && run.outcome === 'failed')
      return matchesQuery && matchesFilter
    })
  }, [filter, query, runs])

  function openRun(run: ResolutionRun) {
    window.history.pushState(null, '', `#operations/${encodeURIComponent(run.id)}`)
    setSelectedRunId(run.id)
  }

  function closeRun() {
    window.history.pushState(null, '', '#operations')
    setSelectedRunId(null)
  }

  if (selectedRun) {
    return (
      <TicketDetail
        generatedAt={overview?.generatedAt}
        health={overview?.health ?? []}
        onBack={closeRun}
        onRefresh={refresh}
        run={selectedRun}
      />
    )
  }

  return (
    <div className="workboard-page">
      <header className="workboard-heading">
        <div>
          <span>Incident operations</span>
          <h1>Incident workboard</h1>
          <p>Every alert, autonomous investigation, and remediation in one queue.</p>
        </div>
        <LiveRefresh generatedAt={overview?.generatedAt} onRefresh={refresh} />
      </header>

      {error && <div className="resolution-error">{error}</div>}

      <section className="workboard-summary" aria-label="Resolution portfolio summary">
        <SummaryMetric label="Total incidents" value={overview?.summary.totalRuns ?? 0} />
        <SummaryMetric label="Active runs" value={overview?.summary.activeRuns ?? 0} tone="blue" />
        <SummaryMetric label="Awaiting review" value={overview?.summary.approvalPending ?? 0} tone="amber" />
        <SummaryMetric label="Failed runs" value={overview?.summary.failedRuns ?? 0} tone="red" />
        <SummaryMetric
          label="Median alert → PR"
          value={formatDuration(overview?.summary.medianTimeToPrSeconds)}
          tone="green"
        />
      </section>

      <section className="workboard-toolbar">
        <label className="workboard-search">
          <Search size={16} />
          <input
            aria-label="Search incidents"
            onChange={event => setQuery(event.target.value)}
            placeholder="Search incident, service, or issue"
            value={query}
          />
        </label>
        <div className="workboard-filters" aria-label="Filter incident runs">
          <ListFilter size={15} />
          {(['all', 'active', 'review', 'failed'] as RunFilter[]).map(option => (
            <button
              className={filter === option ? 'is-active' : ''}
              key={option}
              onClick={() => setFilter(option)}
              type="button"
            >
              {filterLabel(option)}
            </button>
          ))}
        </div>
      </section>

      {loading && !overview ? (
        <div className="resolution-empty"><RefreshCw className="spin" size={18} /> Loading workboard…</div>
      ) : (
        <section className="incident-board" aria-label="Incident workflow board">
          {columns.map(column => {
            const tickets = filteredRuns.filter(run => run.stage === column.id)
            return (
              <div className={`board-column board-column--${column.id}`} key={column.id}>
                <header>
                  <div>
                    <span className="board-column__dot" />
                    <strong>{column.label}</strong>
                    <b>{tickets.length}</b>
                  </div>
                  <small>{column.description}</small>
                </header>
                <div className="board-column__tickets">
                  {tickets.map(run => (
                    <IncidentTicket key={run.id} onOpen={() => openRun(run)} run={run} />
                  ))}
                  {!tickets.length && (
                    <div className="board-column__empty">
                      <CircleDot size={15} /> No incidents in this stage
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </section>
      )}

      <HealthFooter generatedAt={overview?.generatedAt} health={overview?.health ?? []} />
    </div>
  )
}

function IncidentTicket({ run, onOpen }: { run: ResolutionRun; onOpen: () => void }) {
  return (
    <button className={`incident-ticket incident-ticket--${run.outcome}`} onClick={onOpen} type="button">
      <div className="incident-ticket__meta">
        <span className={`severity severity--${run.severity.toLowerCase()}`}>{run.severity}</span>
        <span>{run.id}</span>
        <time>{relativeDate(run.detectedAt)}</time>
      </div>
      <h3>{run.title}</h3>
      <div className="incident-ticket__service"><Server size={13} /> {run.service}</div>

      <WorkflowMiniProgress run={run} />

      <div className="incident-ticket__activity">
        <span className="ticket-owner"><OwnerIcon owner={run.owner} /> {run.owner}</span>
        <small>{run.currentActivity}</small>
      </div>

      <div className="incident-ticket__footer">
        <span><Clock3 size={13} /> {ticketDuration(run)}</span>
        <div>
          {run.issue && <span><FileText size={13} /> #{run.issue.number}</span>}
          {run.pullRequest && <span><GitPullRequest size={13} /> #{run.pullRequest.number}</span>}
        </div>
        <ChevronRight size={16} />
      </div>
    </button>
  )
}

function WorkflowMiniProgress({ run }: { run: ResolutionRun }) {
  const current = stageIndex(run.stage)
  return (
    <div className="ticket-progress" aria-label={`Current stage: ${run.stage}`}>
      {['Alert', 'Issue', 'PR', 'Resolved'].map((label, index) => (
        <div className={index <= current ? 'is-complete' : ''} key={label}>
          <span>{index < current ? <Check size={10} /> : index + 1}</span>
          <small>{label}</small>
        </div>
      ))}
    </div>
  )
}

function TicketDetail({
  run,
  health,
  generatedAt,
  onBack,
  onRefresh,
}: {
  run: ResolutionRun
  health: OperationsOverview['health']
  generatedAt?: string
  onBack: () => void
  onRefresh: () => Promise<void>
}) {
  return (
    <div className="ticket-detail-page">
      <div className="ticket-detail-nav">
        <button onClick={onBack} type="button"><ArrowLeft size={16} /> Workboard</button>
        <span>/</span><strong>{run.id}</strong>
        <LiveRefresh generatedAt={generatedAt} onRefresh={onRefresh} compact />
      </div>

      <header className="ticket-detail-hero">
        <div className="ticket-detail-hero__main">
          <div className="ticket-detail-hero__meta">
            <span className={`severity severity--${run.severity.toLowerCase()}`}>{run.severity}</span>
            <span>{run.service}</span>
            <span>Detected {formatDateTime(run.detectedAt)}</span>
          </div>
          <h1>{run.title}</h1>
          <p>{run.report.summary}</p>
        </div>
        <div className="ticket-detail-hero__outcome">
          <OutcomeBadge outcome={run.outcome} />
          <strong>{run.currentActivity}</strong>
          <span><OwnerIcon owner={run.owner} /> {run.owner}</span>
        </div>
      </header>

      <WorkflowRail run={run} />

      <div className="ticket-detail-grid">
        <main className="resolution-report">
          <header className="resolution-report__heading">
            <span><Sparkles size={18} /></span>
            <div>
              <small>Compiled from Devin artifacts</small>
              <h2>{run.report.title}</h2>
            </div>
            <div className="resolution-report__sources">
              {run.report.sources.map(source => (
                <a href={source.url} key={source.url} rel="noreferrer" target="_blank">
                  {source.kind === 'triage' ? <FileText size={13} /> : <GitPullRequest size={13} />}
                  {source.label}
                </a>
              ))}
            </div>
          </header>

          <div className="resolution-report__sections">
            {run.report.sections.map(section => (
              <article className={`report-section report-section--${section.key}`} key={section.key}>
                <div className="report-section__marker"><ReportIcon section={section.key} /></div>
                <div>
                  <div className="report-section__heading">
                    <h3>{section.title}</h3>
                    {section.url && (
                      <a href={section.url} rel="noreferrer" target="_blank">
                        {section.source} <ExternalLink size={12} />
                      </a>
                    )}
                  </div>
                  <ReportBody body={section.body} />
                </div>
              </article>
            ))}
          </div>
        </main>

        <aside className="ticket-detail-aside">
          <SignalPanel run={run} />
          <AgentPanel run={run} />
          <ArtifactPanel run={run} />
        </aside>
      </div>

      <ResolutionTimeline run={run} />
      <HealthFooter generatedAt={generatedAt} health={health} />
    </div>
  )
}

function WorkflowRail({ run }: { run: ResolutionRun }) {
  const current = stageIndex(run.stage)
  const steps = [
    { label: 'Alert', detail: formatDuration(0), icon: Radio },
    { label: 'Validated issue', detail: formatDuration(run.durations.toIssueSeconds), icon: FileText },
    { label: 'Pull request', detail: formatDuration(run.durations.toPrSeconds), icon: GitPullRequest },
    { label: 'Resolved', detail: run.stage === 'resolved' ? 'Merged' : 'Pending', icon: CheckCircle2 },
  ]
  return (
    <section className="workflow-rail" aria-label="Incident workflow progress">
      {steps.map((step, index) => {
        const Icon = step.icon
        return (
          <div className={`${index <= current ? 'is-complete' : ''} ${index === current ? 'is-current' : ''}`} key={step.label}>
            <span><Icon size={16} /></span>
            <div><strong>{step.label}</strong><small>{step.detail}</small></div>
          </div>
        )
      })}
    </section>
  )
}

function SignalPanel({ run }: { run: ResolutionRun }) {
  return (
    <section className="detail-panel signal-panel">
      <h2>Production signal</h2>
      <dl>
        <div><dt>Error rate</dt><dd>{run.signals.errorRate}%</dd></div>
        <div><dt>p95 latency</dt><dd>{run.signals.p95LatencyMs.toLocaleString()} ms</dd></div>
        <div><dt>Affected sessions</dt><dd>{run.signals.affectedSessions.toLocaleString()}</dd></div>
        <div><dt>Time to issue</dt><dd>{formatDuration(run.durations.toIssueSeconds)}</dd></div>
        <div><dt>Time to PR</dt><dd>{formatDuration(run.durations.toPrSeconds)}</dd></div>
      </dl>
    </section>
  )
}

function AgentPanel({ run }: { run: ResolutionRun }) {
  const agents = [
    run.triageSession && {
      label: 'Triage Devin',
      detail: sessionStatus(run.triageSession.status, run.triageSession.statusDetail),
      url: run.triageSession.url,
      done: Boolean(run.issue),
    },
    run.remediationSession && {
      label: 'Remediation Devin',
      detail: sessionStatus(run.remediationSession.status, run.remediationSession.statusDetail),
      url: run.remediationSession.url,
      done: Boolean(run.pullRequest),
    },
  ].filter(Boolean) as Array<{ label: string; detail: string; url: string; done: boolean }>

  return (
    <section className="detail-panel agent-panel">
      <h2>Autonomous responders</h2>
      {agents.map(agent => (
        <a href={agent.url} key={agent.label} rel="noreferrer" target="_blank">
          <span className={agent.done ? 'is-done' : ''}>{agent.done ? <Check size={13} /> : <Bot size={13} />}</span>
          <div><strong>{agent.label}</strong><small>{agent.detail}</small></div>
          <ExternalLink size={13} />
        </a>
      ))}
      <div className="agent-gate">
        <span><UserRoundCheck size={14} /></span>
        <div><strong>Human approval gate</strong><small>{run.humanAction}</small></div>
      </div>
    </section>
  )
}

function ArtifactPanel({ run }: { run: ResolutionRun }) {
  return (
    <section className="detail-panel artifact-panel">
      <h2>Linked artifacts</h2>
      {run.issue && (
        <a href={run.issue.url} rel="noreferrer" target="_blank">
          <FileText size={16} /><div><strong>Issue #{run.issue.number}</strong><small>{run.issue.state}</small></div><ExternalLink size={13} />
        </a>
      )}
      {run.pullRequest && (
        <a href={run.pullRequest.url} rel="noreferrer" target="_blank">
          <GitPullRequest size={16} /><div><strong>PR #{run.pullRequest.number}</strong><small>{run.pullRequest.state}</small></div><ExternalLink size={13} />
        </a>
      )}
      <div className="artifact-verification">
        <FileCheck2 size={16} />
        <div><strong>{run.verification.testsPassed ?? 'Tests pending'}</strong><small>{run.verification.buildPassed ? 'Build passed' : 'Build pending'}</small></div>
      </div>
      {run.pullRequest && (
        <a className="artifact-review" href={run.pullRequest.url} rel="noreferrer" target="_blank">
          Review pull request <ChevronRight size={15} />
        </a>
      )}
    </section>
  )
}

function ResolutionTimeline({ run }: { run: ResolutionRun }) {
  return (
    <section className="detail-timeline">
      <header><div><small>Audit trail</small><h2>Resolution timeline</h2></div><span>Elapsed {ticketDuration(run)}</span></header>
      <div>
        {run.milestones.map((milestone, index) => {
          const content = (
            <>
              <span className={`detail-timeline__icon detail-timeline__icon--${milestone.kind}`}><MilestoneIcon kind={milestone.kind} /></span>
              <div><strong>{milestone.label}</strong><small>{formatDateTime(milestone.occurredAt)}</small></div>
              <time>{index === 0 ? 'Start' : `+${formatDuration(milestone.elapsedSeconds)}`}</time>
              {milestone.url && <ExternalLink size={13} />}
            </>
          )
          return milestone.url ? (
            <a href={milestone.url} key={`${milestone.kind}-${milestone.occurredAt}`} rel="noreferrer" target="_blank">{content}</a>
          ) : (
            <div key={`${milestone.kind}-${milestone.occurredAt}`}>{content}</div>
          )
        })}
      </div>
    </section>
  )
}

function ReportBody({ body }: { body: string }) {
  return (
    <div className="report-copy">
      {body.split(/\n\n+/).map((paragraph, index) => {
        const lines = paragraph.split('\n')
        const isList = lines.every(line => /^[-*]\s|^\d+\.\s/.test(line.trim()))
        if (isList) {
          return <ul key={`${index}-${paragraph.slice(0, 12)}`}>{lines.map(line => <li key={line}>{line.replace(/^[-*]\s|^\d+\.\s/, '')}</li>)}</ul>
        }
        return <p key={`${index}-${paragraph.slice(0, 12)}`}>{paragraph}</p>
      })}
    </div>
  )
}

function SummaryMetric({ label, value, tone = 'neutral' }: { label: string; value: string | number; tone?: string }) {
  return <div className={`summary-metric summary-metric--${tone}`}><strong>{value}</strong><span>{label}</span></div>
}

function LiveRefresh({ generatedAt, onRefresh, compact = false }: { generatedAt?: string; onRefresh: () => Promise<void>; compact?: boolean }) {
  return (
    <button className={`live-refresh ${compact ? 'live-refresh--compact' : ''}`} onClick={() => void onRefresh()} type="button">
      <RefreshCw size={14} /><span>Live · {relativeAge(generatedAt)} ago</span>
    </button>
  )
}

function HealthFooter({ health, generatedAt }: { health: OperationsOverview['health']; generatedAt?: string }) {
  return (
    <footer className="resolution-health">
      <div>
        {health.slice(0, 3).map(source => (
          <span key={source.name} title={source.detail}>
            <i className={`health-dot health-dot--${source.status}`} />
            {source.name} <strong>{source.status === 'healthy' ? source.detail : 'Degraded'}</strong>
          </span>
        ))}
      </div>
      <span>Updated {relativeAge(generatedAt)} ago</span>
    </footer>
  )
}

function OutcomeBadge({ outcome }: { outcome: ResolutionRun['outcome'] }) {
  return <span className={`outcome-badge outcome-badge--${outcome}`}>{outcomeLabel(outcome)}</span>
}

function OwnerIcon({ owner }: { owner: string }) {
  return owner.includes('Devin') ? <Bot size={13} /> : owner === 'Completed' ? <CheckCircle2 size={13} /> : <UserRoundCheck size={13} />
}

function ReportIcon({ section }: { section: string }) {
  if (section === 'signal') return <Activity size={16} />
  if (section === 'impact') return <Users size={16} />
  if (section === 'root-cause') return <AlertTriangle size={16} />
  if (section === 'resolution') return <ShieldCheck size={16} />
  if (section === 'verification') return <FileCheck2 size={16} />
  if (section === 'rollout-risk') return <CircleDot size={16} />
  return <FileText size={16} />
}

function MilestoneIcon({ kind }: { kind: ResolutionRun['milestones'][number]['kind'] }) {
  if (kind === 'alert') return <AlertTriangle size={14} />
  if (kind === 'agent' || kind === 'code') return <Bot size={14} />
  if (kind === 'issue') return <FileText size={14} />
  if (kind === 'pull_request') return <GitPullRequest size={14} />
  return <CheckCircle2 size={14} />
}

function runIdFromHash(): string | null {
  const match = window.location.hash.match(/^#operations\/(.+)$/)
  return match ? decodeURIComponent(match[1]) : null
}

function stageIndex(stage: WorkflowStage): number {
  return { alert: 0, issue: 1, pull_request: 2, resolved: 3 }[stage]
}

function ticketDuration(run: ResolutionRun): string {
  if (run.durations.toPrSeconds !== undefined && run.durations.toPrSeconds !== null) {
    return `${formatDuration(run.durations.toPrSeconds)} to PR`
  }
  if (run.durations.toIssueSeconds !== undefined && run.durations.toIssueSeconds !== null) {
    return `${formatDuration(run.durations.toIssueSeconds)} to issue`
  }
  return `${formatDuration(run.elapsedSeconds)} elapsed`
}

function sessionStatus(status: string, detail?: string): string {
  if (detail === 'waiting_for_user') return 'Completed · waiting for review'
  if (detail === 'inactivity') return 'Completed · session suspended'
  return `${humanize(status)}${detail ? ` · ${humanize(detail)}` : ''}`
}

function filterLabel(filter: RunFilter): string {
  return { all: 'All', active: 'Active', review: 'Review', failed: 'Failed' }[filter]
}

function outcomeLabel(outcome: ResolutionRun['outcome']): string {
  return {
    alert_received: 'Alert received',
    triaging: 'Investigating',
    issue_created: 'Issue validated',
    remediating: 'Fix in progress',
    pr_opened: 'PR verification',
    ready_for_review: 'Ready for review',
    merged: 'Resolved',
    failed: 'Needs attention',
  }[outcome]
}

function formatDuration(seconds?: number): string {
  if (seconds === undefined || seconds === null) return '—'
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat('en', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

function relativeDate(value: string): string {
  const diff = Math.max(0, Date.now() - new Date(value).getTime())
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function relativeAge(value?: string): string {
  if (!value) return '—'
  const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000))
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m`
}

function humanize(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase())
}
