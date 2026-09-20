import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Code2,
  ExternalLink,
  FileCheck2,
  FileText,
  GitPullRequest,
  RefreshCw,
  ServerCog,
  TestTube2,
  Users,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import {
  getOperationsOverview,
  type OperationsOverview,
  type ResolutionRun,
} from '../api'

const refreshIntervalMs = 5_000

export function OperationsDashboard() {
  const [overview, setOverview] = useState<OperationsOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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
    // The page is a live read model; fetch immediately, then poll its sources.
    // oxlint-disable-next-line react/set-state-in-effect
    void refresh()
    const timer = window.setInterval(() => void refresh(), refreshIntervalMs)
    return () => window.clearInterval(timer)
  }, [refresh])

  const run = overview?.runs[0]

  return (
    <div className="resolution-page">
      <header className="resolution-heading">
        <div>
          <span>Incident resolution</span>
          <h1>Autonomous recovery, ready for review</h1>
          <p>From production alert to a verified pull request.</p>
        </div>
        <button
          aria-label="Refresh resolution data"
          className="resolution-refresh"
          onClick={() => void refresh()}
          type="button"
        >
          <RefreshCw size={15} />
          Live · 5s
        </button>
      </header>

      {error && <div className="resolution-error">{error}</div>}

      {loading && !run ? (
        <div className="resolution-empty"><RefreshCw className="spin" size={18} /> Loading resolution data…</div>
      ) : run ? (
        <>
          <RunSummary run={run} overview={overview} />

          <div className="resolution-main-grid">
            <ResolutionTimeline run={run} />
            <ReviewPackage run={run} />
          </div>

          <EvidenceStrip run={run} />
          <RecentRuns runs={overview?.runs ?? []} />
          <HealthFooter overview={overview} />
        </>
      ) : (
        <div className="resolution-empty">
          <CircleDot size={18} /> No incident runs have been recorded yet.
        </div>
      )}
    </div>
  )
}

function RunSummary({
  run,
  overview,
}: {
  run: ResolutionRun
  overview: OperationsOverview | null
}) {
  return (
    <section className="run-summary" aria-label="Current incident outcome">
      <div className="run-summary__incident">
        <span className="run-summary__alert"><AlertTriangle size={25} /></span>
        <div>
          <div className="run-summary__title-row">
            <h2>{run.id} · {run.severity}</h2>
            <OutcomeBadge outcome={run.outcome} />
          </div>
          <p>{run.title}</p>
          <small>{formatDateTime(run.detectedAt)} · {run.service}</small>
        </div>
      </div>

      <div className="run-summary__outcomes">
        <OutcomeMetric
          value={formatDuration(run.durations.toIssueSeconds)}
          label="Alert → validated issue"
        />
        <OutcomeMetric
          value={formatDuration(run.durations.toPrSeconds)}
          label="Alert → pull request"
        />
        <div className="run-summary__facts">
          <Fact value={run.verification.testsPassed ?? '—'} label="tests passed" />
          <Fact value={String(overview?.summary.failedRuns ?? 0)} label="failed runs" />
          <Fact value={String(overview?.summary.approvalPending ?? 0)} label="approval pending" />
        </div>
      </div>
    </section>
  )
}

function OutcomeMetric({ value, label }: { value: string; label: string }) {
  return (
    <div className="outcome-metric">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  )
}

function Fact({ value, label }: { value: string; label: string }) {
  return (
    <div className="run-fact">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  )
}

function ResolutionTimeline({ run }: { run: ResolutionRun }) {
  return (
    <section className="resolution-card timeline-card">
      <div className="resolution-card__heading">
        <h2>Resolution timeline</h2>
        <span>Total time to PR: <strong>{formatDuration(run.durations.toPrSeconds)}</strong></span>
      </div>
      <div className="resolution-timeline">
        {run.milestones.map((milestone, index) => {
          const Icon = milestoneIcon(milestone.kind)
          const content = (
            <>
              <time>{formatTime(milestone.occurredAt)}</time>
              <span className={`timeline-icon timeline-icon--${milestone.kind}`}><Icon size={16} /></span>
              <strong>{milestone.label}</strong>
              <span className="timeline-elapsed">
                {index === 0 ? '—' : formatDuration(milestone.elapsedSeconds)}
              </span>
              {milestone.url && <ExternalLink className="timeline-link-icon" size={13} />}
            </>
          )
          return milestone.url ? (
            <a className="timeline-row" href={milestone.url} key={`${milestone.kind}-${milestone.occurredAt}`} rel="noreferrer" target="_blank">
              {content}
            </a>
          ) : (
            <div className="timeline-row" key={`${milestone.kind}-${milestone.occurredAt}`}>
              {content}
            </div>
          )
        })}
      </div>
    </section>
  )
}

function ReviewPackage({ run }: { run: ResolutionRun }) {
  const artifacts = [
    run.triageSession && {
      label: 'Triage session',
      detail: 'Devin analysis and reproduction',
      url: run.triageSession.url,
      icon: Bot,
    },
    run.issue && {
      label: `Issue #${run.issue.number}`,
      detail: 'Root cause and acceptance criteria',
      url: run.issue.url,
      icon: FileText,
    },
    run.pullRequest && {
      label: `PR #${run.pullRequest.number}`,
      detail: 'Proposed fix, tests, and rollout risk',
      url: run.pullRequest.url,
      icon: GitPullRequest,
    },
  ].filter(Boolean) as Array<{
    label: string
    detail: string
    url: string
    icon: typeof Bot
  }>

  return (
    <aside className="resolution-card review-card">
      <div className="resolution-card__heading resolution-card__heading--stacked">
        <h2>Review package</h2>
        <span>Artifacts from this run</span>
      </div>
      <div className="review-artifacts">
        {artifacts.map(artifact => {
          const Icon = artifact.icon
          return (
            <a href={artifact.url} key={artifact.label} rel="noreferrer" target="_blank">
              <span><Icon size={17} /></span>
              <div><strong>{artifact.label}</strong><small>{artifact.detail}</small></div>
              <ExternalLink size={14} />
            </a>
          )
        })}
      </div>
      {run.pullRequest && (
        <a className="review-action" href={run.pullRequest.url} rel="noreferrer" target="_blank">
          Review pull request <ChevronRight size={17} />
        </a>
      )}
    </aside>
  )
}

function EvidenceStrip({ run }: { run: ResolutionRun }) {
  const icons = [Users, CircleDot, ServerCog, CheckCircle2]
  return (
    <section className="evidence-card">
      <h2>Key evidence</h2>
      <div>
        {run.evidence.map((evidence, index) => {
          const Icon = icons[index] ?? FileCheck2
          return (
            <article key={evidence.label}>
              <span><Icon size={17} /></span>
              <div><strong>{evidence.label}</strong><small>{evidence.detail}</small></div>
            </article>
          )
        })}
      </div>
    </section>
  )
}

function RecentRuns({ runs }: { runs: ResolutionRun[] }) {
  return (
    <section className="runs-card">
      <div className="resolution-card__heading">
        <h2>Recent resolution runs</h2>
        <span>{runs.length} total</span>
      </div>
      <div className="runs-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Incident</th>
              <th>Service</th>
              <th>Outcome</th>
              <th>Time to issue</th>
              <th>Time to PR</th>
              <th>Human action</th>
              <th>Completed at</th>
            </tr>
          </thead>
          <tbody>
            {runs.map(run => (
              <tr key={run.id}>
                <td><strong>{run.id}</strong></td>
                <td>{run.service}</td>
                <td><OutcomeBadge outcome={run.outcome} /></td>
                <td>{formatDuration(run.durations.toIssueSeconds)}</td>
                <td>{formatDuration(run.durations.toPrSeconds)}</td>
                <td className="runs-table__action">{run.humanAction}</td>
                <td>{run.completedAt ? formatDateTime(run.completedAt) : 'In progress'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {runs.length === 1 && <p className="runs-card__empty">No additional resolution runs yet.</p>}
    </section>
  )
}

function HealthFooter({ overview }: { overview: OperationsOverview | null }) {
  return (
    <footer className="resolution-health">
      <div>
        {(overview?.health ?? []).slice(0, 3).map(source => (
          <span key={source.name} title={source.detail}>
            <i className={`health-dot health-dot--${source.status}`} />
            {source.name} <strong>{source.status === 'healthy' ? source.detail : 'Degraded'}</strong>
          </span>
        ))}
      </div>
      <span>Updated {relativeAge(overview?.generatedAt)} ago</span>
    </footer>
  )
}

function OutcomeBadge({ outcome }: { outcome: ResolutionRun['outcome'] }) {
  return <span className={`outcome-badge outcome-badge--${outcome}`}>{humanize(outcome)}</span>
}

function milestoneIcon(kind: ResolutionRun['milestones'][number]['kind']) {
  return {
    alert: AlertTriangle,
    agent: Bot,
    issue: FileText,
    code: Code2,
    pull_request: GitPullRequest,
    verified: TestTube2,
  }[kind]
}

function formatDuration(seconds?: number): string {
  if (seconds === undefined || seconds === null) return '—'
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat('en', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(value))
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

function relativeAge(value?: string): string {
  if (!value) return '—'
  const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000))
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m`
}

function humanize(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase())
}
