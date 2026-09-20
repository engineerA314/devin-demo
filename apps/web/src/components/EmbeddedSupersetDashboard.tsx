import { embedDashboard, type EmbeddedDashboard } from '@superset-ui/embedded-sdk'
import { Activity, CircleDollarSign, MousePointerClick, Users } from 'lucide-react'
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

  if (config.mode === 'preview') {
    return <PreviewDashboard />
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

const metrics = [
  {
    label: 'Monthly revenue',
    value: '$428.6K',
    change: '↑ 12.4% vs last month',
    icon: CircleDollarSign,
  },
  {
    label: 'Active customers',
    value: '12,842',
    change: '↑ 8.2% vs last month',
    icon: Users,
  },
  {
    label: 'Engagement rate',
    value: '68.4%',
    change: '↑ 4.1% vs last month',
    icon: MousePointerClick,
  },
  {
    label: 'Net retention',
    value: '112.7%',
    change: '↑ 2.8% vs last month',
    icon: Activity,
  },
]

function PreviewDashboard() {
  return (
    <div className="preview-dashboard" aria-label="Superset dashboard preview">
      <div className="metrics-grid">
        {metrics.map(metric => {
          const Icon = metric.icon
          return (
            <article className="metric-card" key={metric.label}>
              <div className="metric-card__top">
                <span>{metric.label}</span>
                <span className="metric-card__icon">
                  <Icon size={13} />
                </span>
              </div>
              <div className="metric-card__value">{metric.value}</div>
              <div className="metric-card__change">{metric.change}</div>
            </article>
          )
        })}
      </div>

      <div className="chart-grid">
        <article className="chart-card">
          <div className="chart-card__header">
            <div>
              <strong>Revenue growth</strong>
              <span>Monthly recurring revenue</span>
            </div>
            <div className="legend">Revenue</div>
          </div>
          <svg
            className="area-chart"
            viewBox="0 0 620 180"
            preserveAspectRatio="none"
            role="img"
            aria-label="Revenue rises over the last six months"
          >
            <defs>
              <linearGradient id="areaFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="#44ba83" stopOpacity="0.28" />
                <stop offset="100%" stopColor="#44ba83" stopOpacity="0.015" />
              </linearGradient>
            </defs>
            {[30, 70, 110, 150].map(y => (
              <line
                key={y}
                x1="0"
                x2="620"
                y1={y}
                y2={y}
                stroke="#edf0ee"
                strokeWidth="1"
              />
            ))}
            <path
              d="M0,148 C55,142 78,126 125,130 C176,134 199,106 250,111 C301,116 323,77 376,84 C425,91 454,58 499,63 C548,68 573,33 620,37 L620,180 L0,180 Z"
              fill="url(#areaFill)"
            />
            <path
              d="M0,148 C55,142 78,126 125,130 C176,134 199,106 250,111 C301,116 323,77 376,84 C425,91 454,58 499,63 C548,68 573,33 620,37"
              fill="none"
              stroke="#35a974"
              strokeLinecap="round"
              strokeWidth="2.5"
            />
            {[
              [0, 148],
              [125, 130],
              [250, 111],
              [376, 84],
              [499, 63],
              [620, 37],
            ].map(([x, y]) => (
              <circle
                key={x}
                cx={x}
                cy={y}
                fill="#fff"
                r="3.5"
                stroke="#35a974"
                strokeWidth="2"
              />
            ))}
          </svg>
        </article>

        <article className="chart-card">
          <div className="chart-card__header">
            <div>
              <strong>Customer segments</strong>
              <span>By recurring revenue</span>
            </div>
          </div>
          <div className="donut-wrap">
            <div className="donut" />
            <div className="donut-label">
              12.8K
              <span>Total customers</span>
            </div>
          </div>
        </article>
      </div>
    </div>
  )
}
