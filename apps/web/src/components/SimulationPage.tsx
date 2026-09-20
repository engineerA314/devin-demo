import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Gauge,
  Radio,
  Server,
  Users,
  Webhook,
  Zap,
} from 'lucide-react'
import { useState } from 'react'
import { triggerDemoIncident } from '../api'

export function SimulationPage({ onViewResolution }: { onViewResolution: () => void }) {
  const [triggering, setTriggering] = useState(false)
  const [incident, setIncident] = useState<{ id: string; status: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function dispatch() {
    setTriggering(true)
    setError(null)
    try {
      const result = await triggerDemoIncident()
      if (result.status === 'trigger_failed') {
        throw new Error('Devin rejected the incident webhook. Check the automation configuration.')
      }
      setIncident(result)
    } catch (dispatchError) {
      setError(dispatchError instanceof Error ? dispatchError.message : 'Unable to dispatch incident')
    } finally {
      setTriggering(false)
    }
  }

  return (
    <div className="simulation-page">
      <header className="simulation-heading">
        <span>Simulation lab</span>
        <h1>Dispatch a production-style alert</h1>
        <p>Send a Datadog-compatible incident payload into the native Devin triage automation.</p>
      </header>

      <div className="simulation-grid">
        <section className="simulation-scenario">
          <div className="simulation-scenario__heading">
            <span><AlertTriangle size={21} /></span>
            <div>
              <small>Selected scenario · SEV-2</small>
              <h2>Embedded analytics authentication recovery degraded</h2>
            </div>
          </div>

          <dl className="simulation-signals">
            <div><dt><Server size={15} /> Service</dt><dd>superset-embedded</dd></div>
            <div><dt><Gauge size={15} /> Error rate</dt><dd>18.7%</dd></div>
            <div><dt><Clock3 size={15} /> p95 latency</dt><dd>4,280 ms</dd></div>
            <div><dt><Users size={15} /> Affected sessions</dt><dd>1,264</dd></div>
          </dl>

          <div className="simulation-monitor">
            <Radio size={16} />
            <div>
              <strong>Embedded guest token refresh failure rate</strong>
              <code>service:superset-embedded route:/guest-token status:error</code>
            </div>
            <span>&gt; 5% / 5m</span>
          </div>
        </section>

        <aside className="simulation-dispatch">
          <span className="simulation-dispatch__icon"><Webhook size={22} /></span>
          <h2>Start the autonomous response</h2>
          <p>The controller persists the alert, signs the webhook, and hands the evidence to the triage automation.</p>

          <ol>
            <li><span>1</span> Persist incident</li>
            <li><span>2</span> Dispatch triage Devin</li>
            <li><span>3</span> Track artifacts and outcome</li>
          </ol>

          {error && <div className="simulation-error">{error}</div>}

          {incident ? (
            <div className="simulation-success">
              <CheckCircle2 size={18} />
              <div><strong>{incident.id} dispatched</strong><span>Devin triage is now running in the cloud.</span></div>
              <button onClick={onViewResolution} type="button">View resolution <ArrowRight size={15} /></button>
            </div>
          ) : (
            <button className="simulation-button" disabled={triggering} onClick={() => void dispatch()} type="button">
              <Zap size={17} /> {triggering ? 'Dispatching…' : 'Dispatch incident'}
            </button>
          )}
        </aside>
      </div>
    </div>
  )
}
