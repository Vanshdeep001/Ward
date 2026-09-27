import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  Bell, Blocks, Flame, LayoutDashboard, MapPin, MessageSquare, Radar, Search, Server, ShieldAlert, ShieldCheck,
  Sparkles, Target,
} from 'lucide-react'
import { useAlerts, useConnection, useCosts, useFindings, useHealth, useResources, useRules } from '../api/hooks.js'
import { rupeesShort } from '../lib/format.js'
import { WardMark } from './ui.jsx'
import { USE_MOCKS } from '../api/client.js'
import EmergencyModal from './EmergencyModal.jsx'
import ErrorBoundary from './ErrorBoundary.jsx'

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

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
  const { connected } = useConnection()
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
    { to: '/app', label: 'Home', icon: LayoutDashboard, end: true, chip: costs && `${rupeesShort(week / 7)}/d` },
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
      <aside className="lift-text glass-frame scroll-quiet m-2 hidden w-66 shrink-0 flex-col overflow-y-auto rounded-[1.25rem] px-3 pb-3 pt-3.5 text-white md:flex">
        {/* Brand */}
        <div className="flex items-center justify-between px-1">
          <Link to="/" title="Back to the landing page" className="flex items-center gap-2.5 transition hover:opacity-90">
            <WardMark emergency={emergency} />
            <span className="font-display text-[1.4rem] font-semibold tracking-tight">Ward</span>
          </Link>
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
        <p className="mt-5 px-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-white/45">Pinned</p>
        <div className="mt-2 grid grid-cols-3 gap-2">
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

        <p className="mt-6 px-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-white/45">Account</p>
        <nav className="mt-2 space-y-0.5">
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
        <div className="mt-auto space-y-2.5 pt-6">
          {costs && <BudgetMeter costs={costs} />}
          <div className="glass rounded-2xl p-1.5">
            <div className="grid grid-cols-2 gap-1">
              <SpaceButton active={!emergency} dot="bg-arc-300" label="Watching" onClick={() => emergency && setShowEmergency(true)} />
              <SpaceButton active={emergency} dot="bg-coral-300" label="Emergency" icon={Flame} onClick={() => setShowEmergency(true)} />
            </div>
          </div>
          {/* Which account Ward is actually reading — the demo one, or theirs. */}
          <Link
            to="/connect"
            className="flex items-center justify-between gap-2 rounded-xl px-2 py-1.5 text-[11px] font-medium text-white/75 transition hover:bg-white/10 hover:text-white"
          >
            <span className="flex min-w-0 items-center gap-2">
              <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${isError ? 'bg-coral-300' : health ? 'animate-breathe bg-emerald-300' : 'bg-white/40'}`} />
              <span className="truncate">
                {isError ? 'Backend offline'
                  : connected ? `${connected.awsAccountId} · ${connected.region}`
                  : 'Demo account'}
              </span>
            </span>
            <span className="shrink-0 rounded-md bg-black/15 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide">
              {USE_MOCKS ? 'mock' : connected ? 'live' : 'connect'}
            </span>
          </Link>
          <p className="px-2 text-[10.5px] text-white/50">
            {isError ? 'Start the API on :8000' : `Checking every ${emergency ? 5 : 15} min`}
          </p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col md:py-2 md:pr-2">
        {/* Mobile top bar */}
        <div className="lift-text flex items-center gap-3 px-4 pb-3 pt-3 text-white md:hidden">
          <Link to="/" title="Back to the landing page"><WardMark emergency={emergency} /></Link>
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

// The month at a glance: spend so far as a filled bar, with a tick where the current burn
// rate says the month will land.
function BudgetMeter({ costs }) {
  const spentPct = Math.round((costs.monthToDate / costs.budget) * 100)
  const projectedPct = Math.round((costs.projectedMonthEnd / costs.budget) * 100)
  const over = projectedPct > 100
  const now = new Date()
  const daysLeft = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate() - now.getDate()

  return (
    <div className="glass rounded-2xl px-3 py-2.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-white/60">Month to date</span>
        <span className="font-display text-[15px] font-semibold tabular-nums">{rupeesShort(costs.monthToDate)}</span>
      </div>
      <div className="relative mt-2 h-1.5 overflow-hidden rounded-full bg-black/25">
        <div
          className={`h-full rounded-full transition-all duration-700 ${over ? 'bg-coral-300' : 'bg-white/85'}`}
          style={{ width: `${Math.min(spentPct, 100)}%` }}
        />
        <span
          aria-hidden
          title="Projected month end"
          className="absolute top-0 h-full w-px bg-white"
          style={{ left: `${Math.min(projectedPct, 100)}%` }}
        />
      </div>
      <p className="mt-1.5 text-[10.5px] font-semibold text-white/60">
        {spentPct}% of {rupeesShort(costs.budget)} · {over ? `tracking ${projectedPct}%` : `${daysLeft}d left`}
      </p>
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

