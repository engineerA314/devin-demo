import {
  Bell,
  CalendarDays,
  ChevronDown,
  CircleHelp,
  LayoutDashboard,
  LineChart,
  Menu,
  Search,
  Settings,
  Sparkles,
  Users,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import './App.css'
import { getEmbedConfig, type EmbedConfig } from './api'
import { EmbeddedSupersetDashboard } from './components/EmbeddedSupersetDashboard'

const navigation = [
  { label: 'Overview', icon: LayoutDashboard, active: true },
  { label: 'Revenue', icon: LineChart },
  { label: 'Customers', icon: Users },
]

function App() {
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

        <div className="workspace-switcher">
          <div className="workspace-switcher__avatar">AC</div>
          <div className="workspace-switcher__copy">
            <span className="workspace-switcher__label">Workspace</span>
            <strong>Acme, Inc.</strong>
          </div>
          <ChevronDown size={16} />
        </div>

        <nav className="navigation" aria-label="Main navigation">
          <span className="navigation__eyebrow">Analytics</span>
          {navigation.map(item => {
            const Icon = item.icon
            return (
              <button
                className={`navigation__item ${item.active ? 'navigation__item--active' : ''}`}
                key={item.label}
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
            <CircleHelp size={18} />
            Help & support
          </button>
          <button className="navigation__item" type="button">
            <Settings size={18} />
            Settings
          </button>
          <div className="profile-card">
            <div className="profile-card__avatar">JP</div>
            <div>
              <strong>Jun Park</strong>
              <span>Admin</span>
            </div>
            <ChevronDown size={16} />
          </div>
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
      </main>
    </div>
  )
}

export default App
