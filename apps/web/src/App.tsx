import {
  Bell,
  BarChart3,
  CalendarDays,
  ChevronDown,
  PlayCircle,
  Menu,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import './App.css'
import { getEmbedConfig, type EmbedConfig } from './api'
import { EmbeddedSupersetDashboard } from './components/EmbeddedSupersetDashboard'
import { OperationsDashboard } from './components/OperationsDashboard'
import { SimulationPage } from './components/SimulationPage'

const navigation = [
  { label: 'Customer Analytics', icon: BarChart3, view: 'overview' },
  { label: 'Incident Resolution', icon: ShieldCheck, view: 'operations' },
  { label: 'Run Simulation', icon: PlayCircle, view: 'simulation' },
]

type View = 'overview' | 'operations' | 'simulation'

function viewFromHash(): View {
  if (window.location.hash === '#operations') return 'operations'
  if (window.location.hash === '#simulation') return 'simulation'
  return 'overview'
}

function App() {
  const [config, setConfig] = useState<EmbedConfig | null>(null)
  const [configError, setConfigError] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [view, setView] = useState<View>(viewFromHash)

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

  useEffect(() => {
    const syncView = () => setView(viewFromHash())
    window.addEventListener('hashchange', syncView)
    window.addEventListener('popstate', syncView)
    return () => {
      window.removeEventListener('hashchange', syncView)
      window.removeEventListener('popstate', syncView)
    }
  }, [])

  function selectView(nextView: View) {
    setView(nextView)
    const nextHash = nextView === 'overview' ? '' : `#${nextView}`
    window.history.pushState(null, '', `${window.location.pathname}${window.location.search}${nextHash}`)
    setSidebarOpen(false)
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? 'sidebar--open' : ''}`}>
        <div className="brand">
          <div className="brand__mark" aria-hidden="true">
            <Sparkles size={18} strokeWidth={2.4} />
          </div>
          <div>
            <div className="brand__name">Luma</div>
            <div className="brand__descriptor">Customer Intelligence</div>
          </div>
        </div>

        <nav className="navigation" aria-label="Main navigation">
          <span className="navigation__eyebrow">Workspace</span>
          {navigation.map(item => {
            const Icon = item.icon
            return (
              <button
                className={`navigation__item ${item.view === view ? 'navigation__item--active' : ''}`}
                key={item.label}
                onClick={() => {
                  selectView(item.view as View)
                }}
                type="button"
              >
                <Icon size={18} />
                {item.label}
              </button>
            )
          })}
        </nav>

        <div className="sidebar__footer">
          <button className="navigation__item" type="button">
            <Settings size={18} />
            Settings
          </button>
          <span className="sidebar__tagline">Higher uptime.<br />Brighter customers.</span>
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
          {view === 'overview' ? (
            <div className="search">
              <Search size={17} />
              <span>Search customers, reports, and metrics</span>
              <kbd>⌘ K</kbd>
            </div>
          ) : (
            <div className="topbar__status"><span /> All systems operational</div>
          )}
          <div className="topbar__actions">
            {view === 'overview' && (
              <>
                <button className="icon-button" aria-label="Notifications" type="button">
                  <Bell size={19} />
                  <span className="notification-dot" />
                </button>
                <button className="date-control" type="button">
                  <CalendarDays size={17} />
                  Last 30 days
                  <ChevronDown size={15} />
                </button>
              </>
            )}
            {view !== 'overview' && <span className="topbar__avatar">JP</span>}
          </div>
        </header>

        {view === 'operations' ? (
          <OperationsDashboard />
        ) : view === 'simulation' ? (
          <SimulationPage onViewResolution={() => selectView('operations')} />
        ) : (
        <div className="page">
          <div className="page-heading">
            <div>
              <div className="eyebrow">Analytics overview</div>
              <h1>Good morning, Jun</h1>
              <p>Track the health and growth of Acme's customer base.</p>
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
        )}
      </main>
    </div>
  )
}

export default App
