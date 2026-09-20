import {
  Activity,
  ArrowLeft,
  BarChart3,
  Bell,
  CalendarDays,
  ChevronDown,
  FileBarChart,
  FlaskConical,
  HeartPulse,
  Menu,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Users,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import './App.css'
import { getEmbedConfig, type EmbedConfig } from './api'
import { EmbeddedSupersetDashboard } from './components/EmbeddedSupersetDashboard'
import { OperationsDashboard } from './components/OperationsDashboard'
import { SimulationPage } from './components/SimulationPage'

migrateLegacyHashRoute()

function App() {
  const path = window.location.pathname.replace(/\/$/, '') || '/'
  const product = path.startsWith('/incident-resolution')
    ? 'incident'
    : path === '/incident-simulator'
      ? 'simulator'
      : 'customer'

  useEffect(() => {
    document.title = {
      customer: 'Luma · Customer Intelligence',
      incident: 'Incident Autopilot · Devin Control Plane',
      simulator: 'Incident Signal Lab · Demo Event Generator',
    }[product]
  }, [product])

  if (product === 'incident') {
    return <IncidentResolutionProduct />
  }
  if (product === 'simulator') {
    return <IncidentSimulator />
  }
  return <CustomerAnalyticsProduct />
}

function CustomerAnalyticsProduct() {
  const [config, setConfig] = useState<EmbedConfig | null>(null)
  const [configError, setConfigError] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    getEmbedConfig()
      .then(setConfig)
      .catch((error: unknown) => {
        setConfig({ mode: 'preview' })
        setConfigError(
          error instanceof Error ? error.message : 'Unable to load configuration',
        )
      })
  }, [])

  return (
    <div className="app-shell app-shell--customer">
      <aside className={`sidebar ${sidebarOpen ? 'sidebar--open' : ''}`}>
        <a className="brand" href="/customer-analytics">
          <div className="brand__mark" aria-hidden="true">
            <Sparkles size={18} strokeWidth={2.4} />
          </div>
          <div>
            <div className="brand__name">Luma</div>
            <div className="brand__descriptor">Customer Intelligence</div>
          </div>
        </a>

        <nav className="navigation" aria-label="Luma navigation">
          <span className="navigation__eyebrow">Analytics</span>
          <a className="navigation__item navigation__item--active" href="/customer-analytics">
            <BarChart3 size={18} /> Analytics overview
          </a>
          <span className="navigation__item navigation__item--disabled">
            <HeartPulse size={18} /> Customer health
          </span>
          <span className="navigation__item navigation__item--disabled">
            <Users size={18} /> Segments
          </span>
          <span className="navigation__item navigation__item--disabled">
            <FileBarChart size={18} /> Reports
          </span>
        </nav>

        <div className="sidebar__footer">
          <button className="navigation__item" type="button">
            <Settings size={18} /> Settings
          </button>
          <span className="sidebar__tagline">Higher insight.<br />Brighter customers.</span>
        </div>
      </aside>

      {sidebarOpen && (
        <button
          aria-label="Close navigation"
          className="sidebar-backdrop"
          onClick={() => setSidebarOpen(false)}
          type="button"
        />
      )}

      <main className="main-content">
        <header className="topbar">
          <button
            aria-label="Open navigation"
            className="icon-button mobile-menu"
            onClick={() => setSidebarOpen(true)}
            type="button"
          >
            <Menu size={20} />
          </button>
          <div className="search">
            <Search size={17} />
            <span>Search customers, reports, and metrics</span>
            <kbd>⌘ K</kbd>
          </div>
          <div className="topbar__actions">
            <button className="icon-button" aria-label="Notifications" type="button">
              <Bell size={19} />
              <span className="notification-dot" />
            </button>
            <button className="date-control" type="button">
              <CalendarDays size={17} />
              Last 30 days
              <ChevronDown size={15} />
            </button>
          </div>
        </header>

        <div className="page">
          <div className="page-heading">
            <div>
              <div className="eyebrow">Analytics overview</div>
              <h1>Good morning, Jun</h1>
              <p>Track the health and growth of Acme&apos;s customer base.</p>
            </div>
            <div className="status-pill">
              <span className="status-pill__dot" />
              Data synced 2 min ago
            </div>
          </div>

          <section className="analytics-card" aria-labelledby="dashboard-title">
            <div className="analytics-card__header">
              <div>
                <div className="analytics-card__title-row">
                  <h2 id="dashboard-title">Executive overview</h2>
                  <span className="superset-badge">Powered by Superset</span>
                </div>
                <p>Revenue, engagement, and customer health at a glance.</p>
              </div>
              <button className="segment-control" type="button">
                All segments
                <ChevronDown size={15} />
              </button>
            </div>

            <EmbeddedSupersetDashboard config={config} />

            {configError && (
              <div className="preview-note" role="status">
                Preview mode is active because the controller is not reachable.
              </div>
            )}
          </section>

          <footer className="page-footer">
            <span>© 2026 Luma Analytics</span>
            <span>Privacy · Status · Documentation</span>
          </footer>
        </div>
      </main>
    </div>
  )
}

function IncidentResolutionProduct() {
  return (
    <div className="product-shell product-shell--incident">
      <header className="product-header">
        <a className="product-brand" href="/incident-resolution">
          <span><ShieldCheck size={19} /></span>
          <div><strong>Incident Autopilot</strong><small>Devin control plane</small></div>
        </a>
        <div className="product-header__actions">
          <span className="product-system-status"><i /> All systems operational</span>
          <a className="product-utility-link" href="/incident-simulator">
            <FlaskConical size={15} /> Open signal simulator
          </a>
          <span className="topbar__avatar">JP</span>
        </div>
      </header>
      <main className="product-main"><OperationsDashboard /></main>
    </div>
  )
}

function IncidentSimulator() {
  return (
    <div className="product-shell product-shell--simulator">
      <header className="product-header product-header--simulator">
        <a className="product-brand" href="/incident-simulator">
          <span><Activity size={19} /></span>
          <div><strong>Incident Signal Lab</strong><small>Demo event generator</small></div>
        </a>
        <a className="product-utility-link" href="/incident-resolution">
          <ArrowLeft size={15} /> Back to Incident Autopilot
        </a>
      </header>
      <main className="simulator-main">
        <SimulationPage onViewResolution={() => window.location.assign('/incident-resolution')} />
      </main>
    </div>
  )
}

function migrateLegacyHashRoute() {
  const { hash, pathname } = window.location
  if (pathname !== '/') return
  if (hash.startsWith('#operations/')) {
    const id = hash.slice('#operations/'.length)
    window.history.replaceState(null, '', `/incident-resolution/${id}`)
  } else if (hash === '#operations') {
    window.history.replaceState(null, '', '/incident-resolution')
  } else if (hash === '#simulation') {
    window.history.replaceState(null, '', '/incident-simulator')
  } else {
    window.history.replaceState(null, '', '/customer-analytics')
  }
}

export default App
