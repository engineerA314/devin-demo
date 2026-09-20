import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Code2,
  FileSearch,
  Gauge,
  Plus,
  Radio,
  Trash2,
  Users,
  Webhook,
  Zap,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  getSetupStatus,
  sendIncidentEvent,
  type AlertAccepted,
  type AlertPayload,
  type AlertSignal,
  type SetupStatus,
} from '../api'

const cd1Signals: AlertSignal[] = [
  { key: 'chart_timeout_rate', label: 'Chart timeout rate', value: '18.7', unit: '%' },
  { key: 'p95_latency_ms', label: 'p95 chart latency', value: '6320', unit: 'ms' },
  { key: 'affected_tenants', label: 'Affected tenants', value: '14', unit: 'tenants' },
]

const cd1Scenario = {
  id: 'CD-1',
  source: 'datadog',
  title: 'Embedded analytics panels exceed the rendering budget under load',
  service: 'luma-embedded-analytics',
  summary: 'Customer sessions across multiple tenants report intermittent embedded chart render timeouts. Other product interactions remain available, and the alert does not identify an owning component.',
  evidenceSources: [
    'Browser RUM outcomes',
    'Chart-data APM traces',
    'Warehouse query digest',
    'Chart configurations',
    'Service health metrics',
    'Deployment events',
  ],
}

export function SimulationPage({ onViewResolution }: { onViewResolution: () => void }) {
  const [triggering, setTriggering] = useState(false)
  const [incident, setIncident] = useState<AlertAccepted | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [source, setSource] = useState(cd1Scenario.source)
  const [title, setTitle] = useState(cd1Scenario.title)
  const [service, setService] = useState(cd1Scenario.service)
  const [summary, setSummary] = useState(cd1Scenario.summary)
  const [signals, setSignals] = useState<AlertSignal[]>(cd1Signals)
  const [setup, setSetup] = useState<SetupStatus | null>(null)
  const [upstreamIncidentId, setUpstreamIncidentId] = useState<string | null>(null)

  useEffect(() => {
    void getSetupStatus().then(setSetup).catch(() => setSetup(null))
  }, [])

  const preview = useMemo(() => ({
    event_id: `${source}:<delivery-id>`,
    incident_id: `${source}:<incident-id>`,
    event_action: 'trigger',
    source,
    title,
    service,
    signals,
    evidence: {
      summary,
      links: {
        rum: 'observability://cd-1/rum-events',
        apm: 'observability://cd-1/apm-traces',
        changes: 'observability://cd-1/change-events',
      },
    },
    metadata: {
      environment: 'production',
      scenario_id: cd1Scenario.id,
      observability_snapshot_id: 'cd1-prod-window-01',
    },
  }), [service, signals, source, summary, title])

  function updateSignal(index: number, patch: Partial<AlertSignal>) {
    setSignals(current => current.map((signal, signalIndex) => (
      signalIndex === index ? { ...signal, ...patch } : signal
    )))
  }

  async function dispatch() {
    setTriggering(true)
    setError(null)
    setIncident(null)
    const incidentId = `${source}:incident:${crypto.randomUUID()}`
    const triggerEventId = `${source}:event:${crypto.randomUUID()}`
    try {
      const triggerPayload: AlertPayload = {
        event_id: triggerEventId,
        incident_id: incidentId,
        event_action: 'trigger',
        source,
        title,
        service,
        occurred_at: new Date().toISOString(),
        signals: signals.filter(signal => signal.key && signal.label),
        evidence: {
          summary,
          monitor: {
            name: 'Embedded analytics panel rendering budget',
            query: 'service:luma-web event:chart_render env:production',
            threshold: { timeout_rate_percent: 5, window_minutes: 5 },
          },
          links: {
            rum: 'observability://cd-1/rum-events',
            apm: 'observability://cd-1/apm-traces',
            changes: 'observability://cd-1/change-events',
          },
        },
        metadata: {
          environment: 'production',
          simulator: true,
          scenario_id: cd1Scenario.id,
          observability_snapshot_id: 'cd1-prod-window-01',
        },
      }
      const result = await sendIncidentEvent(triggerPayload)
      await sendIncidentEvent(triggerPayload)
      if (result.status === 'dispatch_failed') {
        throw new Error('Devin rejected the session request. Check the API service user permissions.')
      }
      setUpstreamIncidentId(incidentId)
      setIncident({ ...result, duplicate_event_count: result.duplicate_event_count + 1 })
    } catch (dispatchError) {
      setError(dispatchError instanceof Error ? dispatchError.message : 'Unable to dispatch alert')
    } finally {
      setTriggering(false)
    }
  }

  return (
    <div className="simulation-page">
      <header className="simulation-heading">
        <span>Simulation lab</span>
        <h1>Trigger a production-shaped incident</h1>
        <p>Simulate the observability boundary while keeping the diagnosis for Devin to discover.</p>
      </header>

      <section className="incident-scenario-card incident-scenario-card--blind" aria-labelledby="cd1-title">
        <div className="incident-scenario-card__identity">
          <span>{cd1Scenario.id}</span>
          <div>
            <small>Verified Superset scenario · root cause withheld</small>
            <h2 id="cd1-title">Embedded chart rendering degradation</h2>
            <p>The monitor reports customer impact. It does not select a repository or prescribe a fix.</p>
          </div>
        </div>
        <div className="incident-scenario-card__facts">
          <div><Activity size={17} /><span><strong>18.7% timeouts</strong><small>five-minute RUM window</small></span></div>
          <div><Gauge size={17} /><span><strong>6.32s p95</strong><small>chart render latency</small></span></div>
          <div><Users size={17} /><span><strong>14 tenants</strong><small>across six dashboards</small></span></div>
        </div>
        <div className="incident-scenario-card__cause incident-scenario-card__cause--unknown">
          <span>Unknown at alert time</span>
          <p>Host application, gateway, Superset, and the warehouse remain viable hypotheses. Six read-only observability exports let Devin correlate the failure before it opens an issue.</p>
        </div>
        <button className="incident-scenario-card__trigger" disabled={triggering || setup?.liveDispatchReady === false} onClick={() => void dispatch()} type="button">
          <Zap size={16} /> {triggering ? 'Triggering CD-1…' : 'Trigger CD-1 incident'}
        </button>
      </section>

      <div className="simulation-grid simulation-grid--intake">
        <section className="simulation-scenario alert-composer">
          <div className="simulation-scenario__heading">
            <span><AlertTriangle size={21} /></span>
            <div>
              <small>Simulated Datadog boundary</small>
              <h2>Symptom-only incident webhook</h2>
            </div>
            <span className="intake-contract"><Radio size={12} /> POST /api/v1/incidents/events</span>
          </div>

          <div className="alert-form-grid">
            <label>
              <span>Source</span>
              <input onChange={event => setSource(event.target.value)} value={source} />
            </label>
            <label className="alert-form-wide">
              <span>Incident title</span>
              <input onChange={event => setTitle(event.target.value)} value={title} />
            </label>
            <label className="alert-form-wide">
              <span>Affected service</span>
              <input onChange={event => setService(event.target.value)} value={service} />
            </label>
            <label className="alert-form-wide">
              <span>Observed customer impact</span>
              <textarea onChange={event => setSummary(event.target.value)} rows={3} value={summary} />
            </label>
          </div>

          <div className="signal-editor">
            <div className="signal-editor__heading">
              <div><strong>Monitor signals</strong><span>Only values available when the alert fires.</span></div>
              <button onClick={() => setSignals(current => [...current, { key: '', label: '', value: '', unit: '' }])} type="button">
                <Plus size={13} /> Add signal
              </button>
            </div>
            {signals.map((signal, index) => (
              <div className="signal-editor__row" key={`${index}-${signal.key}`}>
                <input aria-label="Signal key" onChange={event => updateSignal(index, { key: event.target.value })} placeholder="metric_key" value={signal.key} />
                <input aria-label="Signal label" onChange={event => updateSignal(index, { label: event.target.value })} placeholder="Label" value={signal.label} />
                <input aria-label="Signal value" onChange={event => updateSignal(index, { value: event.target.value })} placeholder="Value" value={signal.value} />
                <input aria-label="Signal unit" onChange={event => updateSignal(index, { unit: event.target.value })} placeholder="Unit" value={signal.unit ?? ''} />
                <button aria-label="Remove signal" disabled={signals.length === 1} onClick={() => setSignals(current => current.filter((_, signalIndex) => signalIndex !== index))} type="button">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </section>

        <aside className="simulation-dispatch">
          <span className="simulation-dispatch__icon"><Webhook size={22} /></span>
          <h2>Start at the observability boundary</h2>
          <p>Detection and paging remain upstream. The demo supplies deterministic exports of the views Devin would read through production observability APIs.</p>

          <div className="snapshot-source-list">
            <div><FileSearch size={14} /><strong>Investigation snapshot</strong><span>6 sources · read only</span></div>
            <ul>{cd1Scenario.evidenceSources.map(item => <li key={item}>{item}</li>)}</ul>
          </div>

          {setup && (
            <div className={`setup-readiness ${setup.liveDispatchReady ? 'setup-readiness--ready' : 'setup-readiness--missing'}`}>
              <div className="setup-readiness__heading">
                {setup.liveDispatchReady ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
                <strong>{setup.liveDispatchReady ? 'Ready for live dispatch' : 'Live credentials required'}</strong>
              </div>
              <span>{setup.repositories?.join(' · ') ?? setup.repository}</span>
              <span>
                {setup.issueIntakeMode === 'polling'
                  ? `GitHub polling · every ${setup.pollIntervalSeconds}s · no webhook secret`
                  : `Signed webhook · ${setup.pollIntervalSeconds}s polling recovery`}
              </span>
              {setup.requiredActions.map(action => <code key={action}>{action}</code>)}
            </div>
          )}

          <ol>
            <li><span>1</span> Receive the symptom-only monitor trigger</li>
            <li><span>2</span> Deduplicate the repeated delivery</li>
            <li><span>3</span> Give Devin the linked read-only exports</li>
            <li><span>4</span> Gate issue creation on executed reproduction, evidence, and confidence</li>
          </ol>

          <details className="payload-preview">
            <summary><Code2 size={13} /> Inspect webhook payload</summary>
            <pre>{JSON.stringify(preview, null, 2)}</pre>
          </details>

          {error && <div className="simulation-error">{error}</div>}

          {incident ? (
            <div className="simulation-success">
              <CheckCircle2 size={18} />
              <div>
                <strong>{incident.id} accepted</strong>
                <span>
                  {incident.event_count} unique event and {incident.duplicate_event_count} duplicate delivery → one workflow · Devin session {incident.session_id ?? 'is being queued'}.
                </span>
                {upstreamIncidentId && <code>{upstreamIncidentId}</code>}
              </div>
              <button onClick={onViewResolution} type="button">View workboard <ArrowRight size={15} /></button>
            </div>
          ) : (
            <button className="simulation-button" disabled={triggering || setup?.liveDispatchReady === false || !title || !service || !source} onClick={() => void dispatch()} type="button">
              <Zap size={17} /> {triggering ? 'Triggering CD-1…' : 'Trigger CD-1 incident'}
            </button>
          )}
        </aside>
      </div>
    </div>
  )
}
