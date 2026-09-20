import { embedDashboard, type EmbeddedDashboard } from '@superset-ui/embedded-sdk'
import { useEffect, useRef, useState } from 'react'
import { fetchGuestToken, type EmbedConfig } from '../api'

type Props = {
  config: EmbedConfig | null
}

export function EmbeddedSupersetDashboard({ config }: Props) {
  const mountRef = useRef<HTMLDivElement>(null)
  const [embedState, setEmbedState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (
      config?.mode !== 'embedded' ||
      !config.dashboardId ||
      !config.supersetDomain ||
      !mountRef.current
    ) {
      return
    }

    let cancelled = false
    let dashboard: EmbeddedDashboard | undefined
    setEmbedState('loading')
    setError(null)

    embedDashboard({
      id: config.dashboardId,
      supersetDomain: config.supersetDomain,
      mountPoint: mountRef.current,
      fetchGuestToken,
      dashboardUiConfig: {
        hideTitle: true,
        hideTab: true,
        hideChartControls: true,
        filters: { expanded: false },
        urlParams: { standalone: 3 },
      },
      iframeTitle: 'Acme executive analytics dashboard',
      referrerPolicy: 'strict-origin-when-cross-origin',
    })
      .then(instance => {
        if (cancelled) {
          instance.unmount()
          return
        }
        dashboard = instance
        setEmbedState('ready')
      })
      .catch((embedError: unknown) => {
        if (cancelled) return
        setEmbedState('error')
        setError(
          embedError instanceof Error
            ? embedError.message
            : 'Unable to load the embedded dashboard',
        )
      })

    return () => {
      cancelled = true
      dashboard?.unmount()
    }
  }, [config])

  if (!config) {
    return (
      <div className="embedded-dashboard">
        <DashboardState title="Loading analytics" />
      </div>
    )
  }

  if (config.mode === 'unconfigured') {
    return (
      <div className="embedded-dashboard">
        <DashboardState
          title="Superset is not connected"
          description="Set the Superset connection in .env and restart Docker to load this dashboard."
        />
      </div>
    )
  }

  return (
    <div className="embedded-dashboard">
      <div className="embedded-dashboard__mount" ref={mountRef} />
      {embedState === 'loading' && <DashboardState title="Connecting to Superset" />}
      {embedState === 'error' && (
        <DashboardState
          title="Dashboard unavailable"
          description={error ?? 'Check the Superset connection and try again.'}
        />
      )}
    </div>
  )
}

function DashboardState({
  title,
  description = 'Preparing the latest customer data.',
}: {
  title: string
  description?: string
}) {
  return (
    <div className="embedded-dashboard__state" role="status">
      <div>
        <div className="spinner" />
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
    </div>
  )
}
