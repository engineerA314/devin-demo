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
  Network,
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
  { id: 'alert', label: 'Incident', description: 'Lifecycle intake' },
  { id: 'attribution', label: 'Attribution', description: 'Component & repository' },
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
  const [selectedRunId, setSelectedRunId] = useState(runIdFromPath)

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
  }, [refresh])

  useEffect(() => {
    const timer = window.setInterval(() => void refresh(), refreshIntervalMs)
    return () => window.clearInterval(timer)
  }, [refresh])

  useEffect(() => {
    const syncSelection = () => {
      setSelectedRunId(runIdFromPath())
    }
    window.addEventListener('popstate', syncSelection)
    return () => {
      window.removeEventListener('popstate', syncSelection)
    }
  }, [])

  const runs = useMemo(() => overview?.runs ?? [], [overview])
  const selectedRun = runs.find(run => run.id === selectedRunId)
  const filteredRuns = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return runs.filter(run => {
      const matchesQuery = !normalizedQuery || [run.id, run.title, run.service, run.repository, run.sourceName, run.issue?.title]
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
    window.history.pushState(null, '', `/incident-resolution/${encodeURIComponent(run.id)}`)
    setSelectedRunId(run.id)
  }

  function closeRun() {
    window.history.pushState(null, '', '/incident-resolution')
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
          <p>One durable engineering workflow for every qualified production incident.</p>
        </div>
        <LiveRefresh generatedAt={overview?.generatedAt} onRefresh={refresh} />
      </header>

      {error && <div className="resolution-error">{error}</div>}

      <section className="workboard-summary" aria-label="Resolution portfolio summary">
        <SummaryMetric label="Pending agent work" value={overview?.summary.pendingAgentWork ?? 0} tone="blue" />
        <SummaryMetric label="Dispatch failure rate" value={formatPercent(overview?.summary.dispatchFailureRate)} />
        <SummaryMetric
          label="CI pass rate"
          value={formatPercent(overview?.summary.ciPassRate)}
          tone="green"
        />
        <SummaryMetric label="CI feedback retries" value={overview?.summary.ciFeedbackRetries ?? 0} tone="amber" />
        <SummaryMetric
          label="Median incident → PR"
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
        <span>{run.id}</span>
        {run.sourceType === 'alert' && <span>{run.eventCount} events</span>}
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
  const labels = [
    run.sourceType === 'issue' ? 'Intake' : 'Incident',
    'Attribution',
    'Issue',
    'PR',
    'Resolved',
  ]
  return (
    <div className="ticket-progress" aria-label={`Current stage: ${run.stage}`}>
      {labels.map((label, index) => (
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
        <div className="ticket-detail-nav__actions">
          <LiveRefresh generatedAt={generatedAt} onRefresh={onRefresh} compact />
        </div>
      </div>

      <header className="ticket-detail-hero">
        <div className="ticket-detail-hero__main">
          <div className="ticket-detail-hero__meta">
            <span>{run.sourceType === 'issue' ? 'GitHub issue' : run.sourceName}</span>
            <span>{run.service}</span>
            {run.sourceType === 'alert' && <span>{humanize(run.incidentStatus)} · {run.eventCount} events</span>}
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
      {run.sourceType === 'alert' && <InvestigationFlow run={run} />}

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
          {run.sourceType === 'alert' && <ObservabilityPanel run={run} />}
          {run.sourceType === 'alert' && <AttributionPanel run={run} />}
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
    { label: run.sourceType === 'issue' ? 'Issue intake' : 'Incident', detail: run.sourceType === 'issue' ? formatDuration(0) : `${run.eventCount} events`, icon: Radio },
    { label: 'Attribution', detail: formatDuration(run.durations.toAttributionSeconds), icon: Network },
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

function InvestigationFlow({ run }: { run: ResolutionRun }) {
  const snapshot = run.observability
  const attributed = Boolean(run.attribution.completedAt)
  return (
    <section className="investigation-flow" aria-label="Evidence to attribution flow">
      <div className="investigation-flow__step is-complete">
        <span><Radio size={15} /></span>
        <div><small>1 · Alert</small><strong>Customer impact observed</strong><p>{run.signals.length} monitor signals · cause unknown</p></div>
      </div>
      <ChevronRight className="investigation-flow__arrow" size={17} />
      <div className={`investigation-flow__step ${snapshot ? 'is-complete' : ''}`}>
        <span><FileCheck2 size={15} /></span>
        <div><small>2 · Evidence</small><strong>{snapshot ? `${snapshot.artifacts.length} views linked` : 'Awaiting evidence'}</strong><p>{snapshot?.provider ?? 'No snapshot attached'}</p></div>
      </div>
      <ChevronRight className="investigation-flow__arrow" size={17} />
      <div className={`investigation-flow__step ${attributed ? 'is-complete' : 'is-active'}`}>
        <span>{attributed ? <Check size={15} /> : <Bot size={15} />}</span>
        <div><small>3 · Attribution</small><strong>{run.attribution.primary_component ?? 'Devin comparing hypotheses'}</strong><p>{attributed ? `${formatConfidence(run.attribution.confidence)} confidence` : 'No repository assumed'}</p></div>
      </div>
    </section>
  )
}

function ObservabilityPanel({ run }: { run: ResolutionRun }) {
  const snapshot = run.observability
  if (!snapshot) return null
  return (
    <section className="detail-panel evidence-panel">
      <div className="evidence-panel__heading">
        <div><small>Read-only snapshot</small><h2>Investigation evidence</h2></div>
        <span className={snapshot.status === 'reviewed' ? 'is-reviewed' : ''}>{humanize(snapshot.status)}</span>
      </div>
      <p>{snapshot.provider} · {formatDateTime(snapshot.window.start)}–{new Intl.DateTimeFormat('en', { hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(snapshot.window.end))}</p>
      <ul>
        {snapshot.artifacts.map(artifact => (
          <li key={artifact.id}>
            <FileCheck2 size={13} />
            <div><strong>{artifact.label}</strong><small>{artifact.source} · {artifact.record_count.toLocaleString()} records</small></div>
          </li>
        ))}
      </ul>
      <footer>Simulated provider export; diagnosis is generated by Devin.</footer>
    </section>
  )
}

function AttributionPanel({ run }: { run: ResolutionRun }) {
  const attribution = run.attribution
  return (
    <section className="detail-panel attribution-panel">
      <h2>System attribution</h2>
      <dl>
        <div><dt>Decision</dt><dd>{humanize(attribution.status)}</dd></div>
        <div><dt>Component</dt><dd>{attribution.primary_component ?? 'Investigating'}</dd></div>
        <div><dt>Repository</dt><dd>{attribution.primary_repository ?? 'Unassigned'}</dd></div>
        <div><dt>Confidence</dt><dd>{formatConfidence(attribution.confidence)}</dd></div>
        <div><dt>Reproduction</dt><dd>{attribution.reproduction ? humanize(attribution.reproduction.status) : 'Pending'}</dd></div>
        <div>
          <dt>Related</dt>
          <dd>{attribution.related_components?.map(item => item.component).join(', ') || 'None'}</dd>
        </div>
      </dl>
      {attribution.policy_reason && <p>{attribution.policy_reason}</p>}
      {attribution.reproduction?.result && <p>{attribution.reproduction.result}</p>}
      {attribution.evidence?.length ? (
        <ul>{attribution.evidence.slice(0, 3).map(item => <li key={item}>{item}</li>)}</ul>
      ) : null}
    </section>
  )
}

function SignalPanel({ run }: { run: ResolutionRun }) {
  return (
    <section className="detail-panel signal-panel">
      <h2>{run.sourceType === 'issue' ? 'Workflow intake' : 'Incident intake'}</h2>
      <dl>
        {run.sourceType === 'alert' && <div><dt>Upstream status</dt><dd>{humanize(run.incidentStatus)}</dd></div>}
        {run.sourceType === 'alert' && <div><dt>Source events</dt><dd>{run.eventCount}</dd></div>}
        {run.sourceType === 'alert' && <div><dt>Duplicate deliveries</dt><dd>{run.duplicateEventCount}</dd></div>}
        {run.signals.map(signal => (
          <div key={signal.key}>
            <dt>{signal.label}</dt>
            <dd>{formatSignalValue(signal.value)}{signal.unit ? ` ${signal.unit}` : ''}</dd>
          </div>
        ))}
        {!run.signals.length && <div><dt>Source</dt><dd>GitHub issue</dd></div>}
        <div><dt>Time to issue</dt><dd>{formatDuration(run.durations.toIssueSeconds)}</dd></div>
        <div><dt>Time to PR</dt><dd>{formatDuration(run.durations.toPrSeconds)}</dd></div>
      </dl>
    </section>
  )
}

function AgentPanel({ run }: { run: ResolutionRun }) {
  const agents = [
    run.triageSession && {
      label: 'Attribution Devin',
      detail: sessionStatus(run.triageSession.status, run.triageSession.statusDetail),
      url: run.triageSession.url,
      done: Boolean(run.attribution.completedAt),
    },
    run.issueSession && {
      label: 'Issue Devin',
      detail: sessionStatus(run.issueSession.status, run.issueSession.statusDetail),
      url: run.issueSession.url,
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
        <div><strong>{run.verification.testsPassed ?? 'Tests pending'}</strong><small>{run.verification.buildPassed ? 'Quality gates passed' : 'Quality gates pending'}</small></div>
      </div>
      {run.pullRequest && (
        <div className={`artifact-ci artifact-ci--${run.ci.status}`}>
          <FileCheck2 size={16} />
          <div>
            <strong>{ciStatusLabel(run.ci.status)}</strong>
            <small>
              {run.ci.status === 'failed'
                ? `${run.ci.feedbackAttempts}/${run.ci.maxFeedbackAttempts} feedback attempts`
                : run.ci.headSha ? `Commit ${run.ci.headSha.slice(0, 7)}` : 'Waiting for commit checks'}
            </small>
            {run.ci.failedChecks.slice(0, 3).map(check => (
              check.url ? (
                <a href={check.url} key={`${check.name}-${check.conclusion}`} rel="noreferrer" target="_blank">
                  {check.name}: {humanize(check.conclusion ?? check.status)} <ExternalLink size={11} />
                </a>
              ) : <span key={`${check.name}-${check.conclusion}`}>{check.name}: {humanize(check.conclusion ?? check.status)}</span>
            ))}
            {run.ci.feedbackError && <span>Feedback dispatch failed: {run.ci.feedbackError}</span>}
          </div>
        </div>
      )}
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

function HealthFooter({
  health,
  generatedAt,
}: {
  health: OperationsOverview['health']
  generatedAt?: string
}) {
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
  if (section === 'observability') return <FileCheck2 size={16} />
  if (section === 'impact') return <Users size={16} />
  if (section === 'attribution') return <Network size={16} />
  if (section === 'root-cause') return <AlertTriangle size={16} />
  if (section === 'resolution') return <ShieldCheck size={16} />
  if (section === 'verification') return <FileCheck2 size={16} />
  if (section === 'rollout-risk') return <CircleDot size={16} />
  return <FileText size={16} />
}

function MilestoneIcon({ kind }: { kind: ResolutionRun['milestones'][number]['kind'] }) {
  if (kind === 'alert') return <AlertTriangle size={14} />
  if (kind === 'evidence') return <FileCheck2 size={14} />
  if (kind === 'attribution') return <Network size={14} />
  if (kind === 'agent' || kind === 'code') return <Bot size={14} />
  if (kind === 'issue') return <FileText size={14} />
  if (kind === 'pull_request') return <GitPullRequest size={14} />
  return <CheckCircle2 size={14} />
}

function runIdFromPath(): string | null {
  const match = window.location.pathname.match(/^\/incident-resolution\/([^/]+)\/?$/)
  return match ? decodeURIComponent(match[1]) : null
}

function stageIndex(stage: WorkflowStage): number {
  return { alert: 0, attribution: 1, issue: 2, pull_request: 3, resolved: 4 }[stage]
}

function ticketDuration(run: ResolutionRun): string {
  if (run.status === 'active' && ['attributing', 'issue_authoring', 'remediating'].includes(run.outcome)) {
    return `${formatDuration(run.elapsedSeconds)} elapsed`
  }
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
    alert_received: 'Incident received',
    attributing: 'Attributing cause',
    issue_authoring: 'Issue validation',
    attribution_review: 'Attribution review',
    non_code: 'Non-code incident',
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

function formatSignalValue(value: string | number): string {
  if (typeof value === 'number') return value.toLocaleString()
  const numeric = Number(value)
  return value.trim() && Number.isFinite(numeric) ? numeric.toLocaleString() : value
}

function formatConfidence(value?: number): string {
  return value === undefined ? '—' : `${Math.round(value * 100)}%`
}

function formatPercent(value?: number | null): string {
  return value === undefined || value === null ? '—' : `${value.toFixed(1)}%`
}

function ciStatusLabel(status: ResolutionRun['ci']['status']): string {
  return {
    not_configured: 'No GitHub CI configured',
    pending: 'GitHub CI running',
    failed: 'GitHub CI failed',
    passed: 'GitHub CI passed',
  }[status]
}
