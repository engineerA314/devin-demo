import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Code2,
  Plus,
  Radio,
  Trash2,
  Webhook,
  Zap,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import {
  triggerAlert,
  type AlertAccepted,
  type AlertPayload,
  type AlertSignal,
} from '../api'

const defaultSignals: AlertSignal[] = [
  { key: 'error_rate', label: 'Error rate', value: '18.7', unit: '%' },
  { key: 'p95_latency_ms', label: 'p95 latency', value: '4280', unit: 'ms' },
  { key: 'affected_sessions', label: 'Affected sessions', value: '1264', unit: '' },
]

export function SimulationPage({ onViewResolution }: { onViewResolution: () => void }) {
  const [triggering, setTriggering] = useState(false)
  const [incident, setIncident] = useState<AlertAccepted | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [source, setSource] = useState('datadog')
  const [title, setTitle] = useState('Embedded analytics authentication recovery degraded')
  const [service, setService] = useState('superset-embedded')
  const [severity, setSeverity] = useState<AlertPayload['severity']>('SEV-2')
  const [summary, setSummary] = useState(
    'After a transient guest-token outage, recovering clients retry in synchronized waves. Token endpoint latency and 5xx responses remain elevated after recovery.',
  )
  const [signals, setSignals] = useState<AlertSignal[]>(defaultSignals)

  const preview = useMemo(() => ({
    event_id: `${source}:<delivery-id>`,
    source,
    title,
    service,
    severity,
    signals,
    evidence: { summary },
  }), [service, severity, signals, source, summary, title])

  function updateSignal(index: number, patch: Partial<AlertSignal>) {
    setSignals(current => current.map((signal, signalIndex) => (
      signalIndex === index ? { ...signal, ...patch } : signal
    )))
  }

  async function dispatch() {
    setTriggering(true)
    setError(null)
    setIncident(null)
    const deliveryId = crypto.randomUUID()
    try {
      const result = await triggerAlert({
        event_id: `${source}:${deliveryId}`,
        source,
        title,
        service,
        severity,
        occurred_at: new Date().toISOString(),
        signals: signals.filter(signal => signal.key && signal.label),
        evidence: {
          summary,
          expected: 'The service should recover without synchronized client retry load.',
        },
        metadata: { environment: 'production', simulator: true },
      })
      if (result.status === 'dispatch_failed') {
        throw new Error('Devin rejected the session request. Check the API service user permissions.')
      }
      setIncident(result)
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
        <h1>Send any production alert</h1>
        <p>Exercise the same vendor-neutral intake used by Datadog, Better Stack, or a custom monitor.</p>
      </header>

      <div className="simulation-grid simulation-grid--intake">
        <section className="simulation-scenario alert-composer">
          <div className="simulation-scenario__heading">
            <span><AlertTriangle size={21} /></span>
            <div>
              <small>Alert envelope</small>
              <h2>Operational signal</h2>
            </div>
            <span className="intake-contract"><Radio size={12} /> POST /api/v1/alerts</span>
          </div>

          <div className="alert-form-grid">
            <label>
              <span>Source</span>
              <input onChange={event => setSource(event.target.value)} value={source} />
            </label>
            <label>
              <span>Severity</span>
              <select onChange={event => setSeverity(event.target.value as AlertPayload['severity'])} value={severity}>
                {['SEV-0', 'SEV-1', 'SEV-2', 'SEV-3', 'SEV-4'].map(value => <option key={value}>{value}</option>)}
              </select>
            </label>
            <label className="alert-form-wide">
              <span>Alert title</span>
              <input onChange={event => setTitle(event.target.value)} value={title} />
            </label>
            <label className="alert-form-wide">
              <span>Affected service</span>
              <input onChange={event => setService(event.target.value)} value={service} />
            </label>
            <label className="alert-form-wide">
              <span>Evidence summary</span>
              <textarea onChange={event => setSummary(event.target.value)} rows={3} value={summary} />
            </label>
          </div>

          <div className="signal-editor">
            <div className="signal-editor__heading">
              <div><strong>Signals</strong><span>Metric names and values are schema driven.</span></div>
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
          <h2>Start an isolated workflow run</h2>
          <p>The controller deduplicates the event, stores it, then creates a titled and tagged Devin Cloud session. The returned session ID becomes the correlation key.</p>

          <ol>
            <li><span>1</span> Validate and persist event ID</li>
            <li><span>2</span> Claim one dispatch atomically</li>
            <li><span>3</span> Store Devin session ID</li>
            <li><span>4</span> Reconcile issue and PR artifacts</li>
          </ol>

          <details className="payload-preview">
            <summary><Code2 size={13} /> Inspect payload</summary>
            <pre>{JSON.stringify(preview, null, 2)}</pre>
          </details>

          {error && <div className="simulation-error">{error}</div>}

          {incident ? (
            <div className="simulation-success">
              <CheckCircle2 size={18} />
              <div>
                <strong>{incident.id} accepted</strong>
                <span>{incident.duplicate ? 'Duplicate delivery reused the existing run.' : `Devin session ${incident.session_id ?? 'is being queued'}.`}</span>
              </div>
              <button onClick={onViewResolution} type="button">View workboard <ArrowRight size={15} /></button>
            </div>
          ) : (
            <button className="simulation-button" disabled={triggering || !title || !service || !source} onClick={() => void dispatch()} type="button">
              <Zap size={17} /> {triggering ? 'Creating Devin session…' : 'Dispatch alert'}
            </button>
          )}
        </aside>
      </div>
    </div>
  )
}
