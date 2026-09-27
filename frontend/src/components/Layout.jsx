import { useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { Flame } from 'lucide-react'
import { useResources } from '../api/hooks.js'
import { WardMark } from './ui.jsx'
import EmergencyModal from './EmergencyModal.jsx'
import ErrorBoundary from './ErrorBoundary.jsx'
import Sidebar, { NAV_ACCOUNT, NAV_PINNED } from './Sidebar.jsx'

export default function Layout() {
  const { pathname } = useLocation()
  const { data: resData } = useResources()
  const [showEmergency, setShowEmergency] = useState(false)
  const [emergency, setEmergency] = useState(() => new URLSearchParams(window.location.search).has('emergency'))

  return (
    <div className={`shell flex h-full ${emergency ? 'shell-emergency' : ''}`}>
      <Sidebar emergency={emergency} onEmergency={() => setShowEmergency(true)} />

      <div className="flex min-w-0 flex-1 flex-col md:py-2 md:pr-2">
        {/* Mobile top bar */}
        <div className="lift-text flex items-center gap-3 px-4 pb-3 pt-3 text-white md:hidden">
          <Link to="/" title="Back to the landing page"><WardMark emergency={emergency} /></Link>
          <nav className="-mx-1 flex flex-1 gap-1 overflow-x-auto">
            {[...NAV_PINNED, ...NAV_ACCOUNT].map(({ to, label, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  `whitespace-nowrap rounded-lg px-2.5 py-1.5 text-xs font-bold ${isActive ? 'bg-white text-ink [text-shadow:none]' : 'text-white/90'}`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
          <button onClick={() => setShowEmergency(true)} aria-label="Emergency mode" className="glass rounded-lg p-1.5">
            <Flame size={16} />
          </button>
        </div>

        {/* The page, with arc.net's scalloped seam along its top edge */}
        <div className="cloud-top relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-b-none bg-paper md:rounded-b-[1.25rem]">
          {emergency && (
            <div className="relative z-10 shrink-0">
              <div className="flex flex-wrap items-center justify-between gap-2 bg-coral-500 px-5 pb-2 pt-4 text-xs font-semibold text-white">
                <span className="flex items-center gap-2"><Flame size={14} /> Emergency budget mode — checking every 5 minutes, snooze disabled.</span>
                <button onClick={() => setShowEmergency(true)} className="underline underline-offset-2 hover:no-underline">Review actions</button>
              </div>
              <div className="scallop" style={{ '--scallop': 'var(--color-coral-500)' }} />
            </div>
          )}
          <div className={`pointer-events-none absolute inset-x-0 top-0 h-80 ${emergency ? 'aurora-emergency' : 'aurora'}`} />
          <main className="scroll-quiet relative flex-1 overflow-y-auto">
            <div key={pathname} className="animate-rise mx-auto w-full max-w-6xl px-4 py-9 md:px-10 md:py-11">
              <ErrorBoundary resetKey={pathname}>
                <Outlet />
              </ErrorBoundary>
            </div>
          </main>
        </div>
      </div>

      <EmergencyModal
        isOpen={showEmergency}
        active={emergency}
        onActivate={() => setEmergency(true)}
        onExit={() => {
          setEmergency(false)
          setShowEmergency(false)
        }}
        onClose={() => setShowEmergency(false)}
        resources={resData?.items ?? []}
      />
    </div>
  )
}
