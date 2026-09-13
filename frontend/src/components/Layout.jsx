import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  Bell, Blocks, Flame, LayoutDashboard, MapPin, MessageSquare, Radar, Search, Server, ShieldAlert, ShieldCheck,
  Sparkles, Target,
} from 'lucide-react'
import { useAlerts, useCosts, useFindings, useHealth, useResources, useRules } from '../api/hooks.js'
import { USE_MOCKS } from '../api/client.js'
import EmergencyModal from './EmergencyModal.jsx'
import ErrorBoundary from './ErrorBoundary.jsx'

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
const compactRupees = (n) => (n >= 1000 ? `₹${(n / 1000).toFixed(1)}k` : `₹${Math.round(n)}`)

export default function Layout() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const askRef = useRef(null)
  const { data: health, isError } = useHealth()
  const { data: resData } = useResources()
  const { data: alerts } = useAlerts()
  const { data: costs } = useCosts()
  const { data: findings } = useFindings()
  const { data: rules } = useRules()
  const [ask, setAsk] = useState('')
  const [showEmergency, setShowEmergency] = useState(false)
  const [emergency, setEmergency] = useState(() => new URLSearchParams(window.location.search).has('emergency'))

  // Ctrl/⌘ + K jumps to the Ask bar from anywhere.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        askRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Live status on the pinned tiles, like the "in 3m" chip on Arc's calendar tile.
  const week = costs?.daily.slice(-7).reduce((s, d) => s + d.amount, 0) ?? 0
  const prevWeek = costs?.daily.slice(-14, -7).reduce((s, d) => s + d.amount, 0) ?? 0
  const weekChange = prevWeek ? Math.round(((week - prevWeek) / prevWeek) * 100) : 0
  const urgent = findings?.filter((f) => f.severity === 'urgent').length ?? 0
  const activeRules = rules?.filter((r) => r.status === 'active').length ?? 0
  const openAlerts = alerts?.filter((a) => a.status === 'open').length ?? 0

  const pinned = [
    { to: '/', label: 'Home', icon: LayoutDashboard, end: true, chip: costs && `${compactRupees(week / 7)}/d` },
    { to: '/copilot', label: 'Copilot', icon: MessageSquare },
    { to: '/rules', label: 'Guardrails', icon: ShieldCheck, chip: rules && `${activeRules} on` },
    { to: '/detective', label: 'Detective', icon: Search, chip: costs && weekChange > 0 && `↑${weekChange}%`, hot: weekChange > 25 },
    { to: '/guardian', label: 'Guardian', icon: Radar, dot: urgent },
    { to: '/architect', label: 'Architect', icon: Blocks },
  ]
  const account = [
    { to: '/resources', label: 'Resources', icon: Server, count: resData?.items.length },
    { to: '/alerts', label: 'Alerts', icon: Bell, count: openAlerts, hot: openAlerts > 0 },
    { to: '/health', label: 'Rule health', icon: ShieldAlert },
    { to: '/accuracy', label: 'Prediction accuracy', icon: Target },
  ]

  function submitAsk(e) {
    e.preventDefault()
    if (!ask.trim()) return
    navigate(`/copilot?q=${encodeURIComponent(ask.trim())}`)
    setAsk('')
    askRef.current?.blur()
  }

  return (
    <div className={`shell flex h-full ${emergency ? 'shell-emergency' : ''}`}>
      <aside className="lift-text hidden w-[16.5rem] shrink-0 flex-col px-3 pb-3 pt-4 text-white md:flex">
        {/* Brand */}
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-2.5">
            <WardMark emergency={emergency} />
            <span className="font-display text-[1.4rem] font-semibold tracking-tight">Ward</span>
          </div>
          <span className="glass inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-semibold text-white/90">
            <MapPin size={11} /> Mumbai
          </span>
        </div>

        {/* Command bar */}
        <form onSubmit={submitAsk} className="mt-4">
          <label className="glass group flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm transition focus-within:!bg-white focus-within:text-ink focus-within:[text-shadow:none] focus-within:shadow-[0_8px_24px_-8px_rgb(10_8_60/0.5)]">
            <Sparkles size={15} className="shrink-0 opacity-90" />
            <input
              ref={askRef}
              value={ask}
              onChange={(e) => setAsk(e.target.value)}
              placeholder="Ask Ward anything…"
              className="w-full bg-transparent font-medium outline-none placeholder:text-white/75 focus:placeholder:text-slate-400"
            />
            <kbd className="shrink-0 rounded-md bg-white/15 px-1.5 py-0.5 font-sans text-[10px] font-bold text-white/80 group-focus-within:bg-slate-100 group-focus-within:text-slate-500">
              {isMac ? '⌘K' : 'Ctrl K'}
            </kbd>
          </label>
        </form>

        {/* Pinned tiles */}
        <div className="mt-4 grid grid-cols-3 gap-2">
          {pinned.map(({ to, label, icon: Icon, end, chip, dot, hot }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `relative flex h-[4.4rem] flex-col items-center justify-center gap-1 rounded-2xl text-[11px] font-bold transition duration-200 hover:-translate-y-0.5 ${
                  isActive ? 'glass-active text-ink [text-shadow:none]' : 'glass text-white'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={19} strokeWidth={2.1} className={isActive ? 'text-arc-600' : ''} />
                  {label}
                  {chip && (
                    <span
                      className={`absolute right-1 top-1 rounded-md px-1 text-[9px] font-bold leading-4 [text-shadow:none] ${
                        hot ? 'bg-coral-400 text-white' : isActive ? 'bg-arc-50 text-arc-700' : 'bg-black/20 text-white/90'
                      }`}
                    >
                      {chip}
                    </span>
                  )}
                  {dot > 0 && (
                    <span className="absolute right-1.5 top-1.5 grid h-4 min-w-4 place-items-center rounded-full bg-coral-400 px-1 text-[9px] font-bold text-white ring-2 ring-white/40 [text-shadow:none]">
                      {dot}
                    </span>
                  )}
                </>
              )}
            </NavLink>
          ))}
        </div>

        <div className="mx-2 mt-5 border-t border-white/15" />
        <nav className="mt-3 space-y-0.5">
          {account.map(({ to, label, icon: Icon, count, hot }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-[14px] font-semibold transition ${
                  isActive ? 'glass-active text-ink [text-shadow:none]' : 'text-white/90 hover:bg-white/10'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={16} className={isActive ? 'text-arc-600' : 'opacity-80'} />
                  <span className="flex-1">{label}</span>
                  {count > 0 && (
                    <span
                      className={`rounded-full px-1.5 text-[11px] font-bold tabular-nums [text-shadow:none] ${
                        hot ? 'bg-coral-400 text-white' : isActive ? 'bg-slate-100 text-slate-500' : 'text-white/60'
                      }`}
                    >
                      {count}
                    </span>
                  )}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Spaces, like the coloured dots at the bottom of Arc's sidebar */}
        <div className="mt-auto space-y-2.5">
          <div className="glass rounded-2xl p-1.5">
            <div className="grid grid-cols-2 gap-1">
              <SpaceButton active={!emergency} dot="bg-arc-300" label="Watching" onClick={() => emergency && setShowEmergency(true)} />
              <SpaceButton active={emergency} dot="bg-coral-300" label="Emergency" icon={Flame} onClick={() => setShowEmergency(true)} />
            </div>
          </div>
          <div className="flex items-center justify-between px-2 text-[11px] font-medium text-white/75">
            <span className="flex items-center gap-2">
              <span className={`h-1.5 w-1.5 rounded-full ${isError ? 'bg-coral-300' : health ? 'animate-breathe bg-emerald-300' : 'bg-white/40'}`} />
              {isError ? 'Backend offline' : `Checking every ${emergency ? 5 : 15} min`}
            </span>
            {USE_MOCKS && <span className="rounded-md bg-black/15 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide">mock</span>}
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col md:py-2 md:pr-2">
        {/* Mobile top bar */}
        <div className="lift-text flex items-center gap-3 px-4 pb-3 pt-3 text-white md:hidden">
          <WardMark emergency={emergency} />
          <nav className="-mx-1 flex flex-1 gap-1 overflow-x-auto">
            {[...pinned, ...account].map(({ to, label, end }) => (
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
        <div className="wavy-top relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-b-none bg-paper md:rounded-b-[1.25rem]">
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

function SpaceButton({ active, dot, label, icon: Icon, onClick }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`flex items-center justify-center gap-1.5 rounded-xl px-2 py-2 text-xs font-bold transition ${
        active ? 'bg-white text-ink shadow-[0_4px_12px_-4px_rgb(10_8_60/0.4)] [text-shadow:none]' : 'text-white/85 hover:bg-white/10'
      }`}
    >
      {Icon && active ? <Icon size={13} className="text-coral-500" /> : <span className={`h-2 w-2 rounded-full ${dot} ring-2 ring-white/30`} />}
      {label}
    </button>
  )
}

// Sticker-style mark, after Arc's logo: a scalloped-top shield with a white outline and a warm core.
function WardMark({ emergency }) {
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" aria-hidden className="drop-shadow-[0_2px_3px_rgb(10_8_60/0.35)]">
      <defs>
        <linearGradient id="ward-core" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={emergency ? '#ffd29a' : '#ff9a8b'} />
          <stop offset="55%" stopColor={emergency ? '#ff8a65' : '#ff6f91'} />
          <stop offset="100%" stopColor={emergency ? '#e8463f' : '#7b61ff'} />
        </linearGradient>
      </defs>
      <path
        d="M16 3c1.3 1.1 2.7 1.1 4 0 1.3 1.1 2.7 1.1 4 0 1 .9 2.1 1.1 3.3 1v10.5c0 6.7-4.8 11.1-11.3 14.2C9.5 25.6 4.7 21.2 4.7 14.5V4c1.2.1 2.3-.1 3.3-1 1.3 1.1 2.7 1.1 4 0 1.3 1.1 2.7 1.1 4 0Z"
        fill="url(#ward-core)"
        stroke="#fff"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      <path d="m11 15.8 3.4 3.4 6.8-7" fill="none" stroke="#fff" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
