import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  Bell, Blocks, ChevronsLeft, Eye, Flame, LayoutDashboard, MessageSquare, Pin, Radar, Search, Server, ShieldAlert,
  MessageSquareText, ShieldCheck, Target,
} from 'lucide-react'
import { useAlerts, useConnection, useCosts, useFindings, useHealth, useResources, useRules } from '../api/hooks.js'
import { USE_MOCKS } from '../api/client.js'
import { rupeesShort } from '../lib/format.js'
import { WardMark } from './ui.jsx'

/* The sidebar is a dark instrument deck floating on the indigo shell.

   It folds into a rail four ways — drag its right edge (the panel follows the pointer and *reveals*
   its contents, which are laid out at full width and clipped rather than squashed), click the shield
   or the « button, press [, or, when folded, rest on the rail and the full deck floats out over the
   page without moving it. Folded, the readings survive: the budget becomes a vertical gauge, counts
   become badges. */

export const NAV_PINNED = [
  { to: '/app', label: 'Home', icon: LayoutDashboard, end: true },
  { to: '/copilot', label: 'Copilot', icon: MessageSquare },
  { to: '/rules', label: 'Guardrails', icon: ShieldCheck },
  { to: '/detective', label: 'Detective', icon: Search },
  { to: '/guardian', label: 'Guardian', icon: Radar },
  { to: '/architect', label: 'Architect', icon: Blocks },
]
export const NAV_ACCOUNT = [
  { to: '/resources', label: 'Resources', icon: Server },
  { to: '/alerts', label: 'Alerts', icon: Bell },
  { to: '/health', label: 'Rule health', icon: ShieldAlert },
  { to: '/accuracy', label: 'Prediction accuracy', icon: Target },
]

const OPEN = 264 // px — the deck unfolded
const RAIL = 64 // px — folded
const MID = (OPEN + RAIL) / 2 // a drag released past here opens; short of it, folds
const SPRING = 'ease-[cubic-bezier(0.32,0.72,0,1)]'
const PEEK_DWELL_MS = 450 // passing over the rail on the way to a button shouldn't unfold it
const ROW_REM = 2.25 // height of an Account row, which the light-bar slides by
const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
const FLOATING_SHADOW = '0 32px 90px -20px rgb(4 3 30 / 0.95)' // deeper than the docked one; the edge is .deck::after

const readOpen = () => {
  try {
    return localStorage.getItem('ward.sidebar') !== 'rail'
  } catch {
    return true
  }
}
const saveOpen = (open) => {
  try {
    localStorage.setItem('ward.sidebar', open ? 'open' : 'rail')
  } catch {
    /* private window or blocked storage: the sidebar just won't remember */
  }
}
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))
const isActivePath = (item, pathname) => (item.end ? pathname === item.to : pathname.startsWith(item.to))

export default function Sidebar({ emergency, onEmergency }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const askRef = useRef(null)
  const [ask, setAsk] = useState('')

  const [expanded, setExpanded] = useState(readOpen)
  const expandedRef = useRef(expanded)
  const [peek, setPeek] = useState(false)
  const [dragW, setDragW] = useState(null) // live width while the edge is being dragged
  const drag = useRef(null)
  const suppressClick = useRef(false)
  const peekTimer = useRef()

  const setOpen = (open) => {
    expandedRef.current = open
    setExpanded(open)
    saveOpen(open)
    setPeek(false)
  }

  function focusAsk() {
    if (expandedRef.current) return askRef.current?.focus()
    setOpen(true)
    setTimeout(() => askRef.current?.focus(), 380) // after the unfold, so the caret lands on a visible field
  }

  // Ctrl/⌘ K unfolds and jumps to Ask; [ folds and unfolds — unless you're typing.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        focusAsk()
        return
      }
      const typing = e.target.closest?.('input, textarea, select, [contenteditable="true"]')
      if (e.key === '[' && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault()
        setOpen(!expandedRef.current)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => setPeek(false), [pathname]) // following a link from a peek tucks the deck back

  // ── The draggable edge ───────────────────────────────────────────────────
  const panelW = dragW ?? (expanded || peek ? OPEN : RAIL)
  const wide = dragW != null ? dragW > MID : expanded || peek
  const floating = !expanded && (peek || (dragW != null && dragW > RAIL)) // over the page, not beside it

  const grip = {
    onPointerDown(e) {
      e.currentTarget.setPointerCapture(e.pointerId)
      clearTimeout(peekTimer.current)
      drag.current = { x: e.clientX, w: panelW, moved: false }
    },
    onPointerMove(e) {
      const d = drag.current
      if (!d) return
      const dx = e.clientX - d.x
      if (Math.abs(dx) > 3) d.moved = true
      if (d.moved) setDragW(clamp(d.w + dx, RAIL, OPEN))
    },
    onPointerUp(e) {
      const d = drag.current
      drag.current = null
      if (!d?.moved) return // a plain click: onClick handles it
      suppressClick.current = true
      setDragW(null)
      setOpen(clamp(d.w + (e.clientX - d.x), RAIL, OPEN) > MID)
    },
    onClick() {
      if (suppressClick.current) {
        suppressClick.current = false
        return
      }
      setOpen(!expandedRef.current)
    },
  }

  // ── Live readings ────────────────────────────────────────────────────────
  const { data: health, isError } = useHealth()
  const { data: resData } = useResources()
  const { data: alerts } = useAlerts()
  const { data: costs } = useCosts()
  const { data: findings } = useFindings()
  const { data: rules } = useRules()
  const { connected } = useConnection()

  const week = costs?.daily.slice(-7).reduce((s, d) => s + d.amount, 0) ?? 0
  const prevWeek = costs?.daily.slice(-14, -7).reduce((s, d) => s + d.amount, 0) ?? 0
  const weekChange = prevWeek ? Math.round(((week - prevWeek) / prevWeek) * 100) : 0
  const openAlerts = alerts?.filter((a) => a.status === 'open').length ?? 0
  const urgent = findings?.filter((f) => f.severity === 'urgent').length ?? 0

  const live = {
    '/app': { value: costs && `${rupeesShort(week / 7)}/day` },
    '/rules': { value: rules && `${rules.filter((r) => r.status === 'active').length} on` },
    '/detective': { value: weekChange > 0 ? `↑${weekChange}% this week` : null, hot: weekChange > 25 },
    '/guardian': { value: urgent ? `${urgent} urgent` : null, dot: urgent },
    '/resources': { count: resData?.items.length },
    '/alerts': { count: openAlerts, hot: openAlerts > 0 },
  }
  const pinned = NAV_PINNED.map((item) => ({ ...item, ...live[item.to] }))
  const account = NAV_ACCOUNT.map((item) => ({ ...item, ...live[item.to] }))
  const readings = {
    burn: costs ? rupeesShort(week / 7) : '—',
    openAlerts,
    tone: isError ? 'bg-coral-300' : health ? 'animate-breathe bg-emerald-300' : 'bg-white/40',
    account: isError ? 'Backend offline — start the API on :8000'
      : connected ? `AWS ${connected.awsAccountId} · ${connected.region}` : 'Demo account · ap-south-1',
    tag: USE_MOCKS ? 'mock' : connected ? 'live' : 'demo',
  }

  function submitAsk(e) {
    e.preventDefault()
    if (!ask.trim()) return
    navigate(`/copilot?q=${encodeURIComponent(ask.trim())}`)
    setAsk('')
    askRef.current?.blur()
  }

  return (
    <aside
      className={`relative hidden shrink-0 transition-[width] duration-500 ${SPRING} md:block`}
      style={{ width: (expanded ? OPEN : RAIL) + 16 }}
    >
      <div
        onMouseEnter={() => {
          if (expanded || drag.current) return
          peekTimer.current = setTimeout(() => setPeek(true), PEEK_DWELL_MS)
        }}
        onMouseLeave={() => {
          clearTimeout(peekTimer.current)
          if (!drag.current) setPeek(false)
        }}
        onMouseDown={() => clearTimeout(peekTimer.current)} // clicking a rail icon shouldn't also unfold it
        className={`deck ${emergency ? 'deck-emergency' : ''} absolute bottom-2 left-2 top-2 z-40 overflow-hidden rounded-[1.25rem] text-white ${
          dragW == null ? `transition-[width,box-shadow] duration-500 ${SPRING}` : ''
        }`}
        // Inline, because .deck is unlayered CSS and would beat a Tailwind shadow class.
        style={{ width: panelW, ...(floating && { boxShadow: FLOATING_SHADOW }) }}
      >
        {/* `inert` on whichever half is hidden: invisible links must not be reachable by Tab either. */}
        <div
          inert={wide ? undefined : ''}
          className={`scroll-quiet flex h-full w-[264px] flex-col overflow-y-auto px-3.5 pb-3.5 pt-4 transition-opacity ${
            wide ? 'opacity-100 delay-100 duration-300' : 'pointer-events-none opacity-0 duration-150'
          }`}
        >
          <Full
            {...{ emergency, onEmergency, pinned, account, pathname, costs, readings, ask, setAsk, askRef, submitAsk, expanded }}
            onShield={() => setOpen(!expanded)} // unfolded, it folds; peeking, it pins the deck open
          />
        </div>

        <div
          inert={wide ? '' : undefined}
          className={`scroll-quiet absolute inset-y-0 left-0 flex w-16 flex-col items-center overflow-y-auto pb-3.5 pt-4 transition-opacity ${
            wide ? 'pointer-events-none opacity-0 duration-150' : 'opacity-100 delay-150 duration-300'
          }`}
        >
          <Rail {...{ emergency, onEmergency, pinned, account, pathname, costs, readings }} onUnfold={() => setOpen(true)} onAsk={focusAsk} />
        </div>

        {/* The edge you pull: invisible until hovered, then a thin line of light. */}
        <button
          type="button"
          aria-label={expanded ? 'Fold the sidebar (or press [)' : 'Unfold the sidebar (or press [)'}
          aria-expanded={expanded}
          title="Drag to fold or unfold · ["
          {...grip}
          className="group absolute inset-y-0 right-0 z-20 w-2 cursor-col-resize touch-none"
        >
          <span className="absolute inset-y-8 right-0 w-px bg-white/0 transition duration-300 group-hover:bg-white/80 group-hover:shadow-[0_0_12px_2px_rgb(255_255_255/0.6)] group-active:bg-white" />
        </button>
      </div>
    </aside>
  )
}

/* ── Unfolded ─────────────────────────────────────────────────────────────── */

function Full({ emergency, onEmergency, pinned, account, pathname, costs, readings, ask, setAsk, askRef, submitAsk, onShield, expanded }) {
  const beam = useSticky(account.findIndex((item) => isActivePath(item, pathname)))

  return (
    <>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ShieldToggle emergency={emergency} expanded={expanded} onClick={onShield} />
          <Link to="/" title="Back to the landing page" className="font-display text-[1.35rem] font-semibold tracking-tight transition hover:text-white/80">
            Ward
          </Link>
        </div>
        <button
          type="button"
          onClick={onShield}
          aria-label={expanded ? 'Fold the sidebar' : 'Keep the sidebar open'}
          title={expanded ? 'Fold · [' : 'Keep open'}
          className="grid h-8 w-8 place-items-center rounded-lg text-white/40 transition hover:bg-white/10 hover:text-white"
        >
          {expanded ? <ChevronsLeft size={17} /> : <Pin size={15} />}
        </button>
      </div>

      <form onSubmit={submitAsk} className="mt-4">
        <label className="group flex items-center gap-2 rounded-xl bg-white/[0.06] px-3 py-2.5 text-sm ring-1 ring-inset ring-white/10 transition focus-within:bg-white/[0.1] focus-within:ring-white/50">
          <MessageSquareText size={15} className="shrink-0 text-white/80" />
          <input
            ref={askRef}
            value={ask}
            onChange={(e) => setAsk(e.target.value)}
            placeholder="Ask Ward anything…"
            className="w-full bg-transparent font-medium text-white outline-none placeholder:text-white/40"
          />
          <kbd className="shrink-0 rounded-md bg-white/10 px-1.5 py-0.5 font-sans text-[10px] font-bold text-white/55">
            {isMac ? '⌘K' : 'Ctrl K'}
          </kbd>
        </label>
      </form>

      {/* The account at a glance — the two numbers people actually open Ward to check. */}
      <Link to="/connect" className="deck-well mt-3 block rounded-2xl px-3.5 py-3 transition hover:brightness-125">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.16em] text-white/50">
            <span className={`h-1.5 w-1.5 rounded-full ${readings.tone}`} />
            {emergency ? 'Emergency' : 'Watching'} · {emergency ? 5 : 15} min
          </span>
          <span className="rounded-md bg-white/10 px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wide text-white/70">
            {readings.tag}
          </span>
        </div>
        <div className="mt-3 grid grid-cols-2 divide-x divide-white/10">
          <div className="pr-3">
            <p className="font-display text-[1.6rem] font-semibold leading-none">{readings.burn}</p>
            <p className="mt-1.5 text-[10.5px] text-white/45">per day</p>
          </div>
          <div className="pl-3">
            <p className={`font-display text-[1.6rem] font-semibold leading-none ${readings.openAlerts ? 'text-coral-300' : ''}`}>
              {readings.openAlerts}
            </p>
            <p className="mt-1.5 text-[10.5px] text-white/45">open alert{readings.openAlerts === 1 ? '' : 's'}</p>
          </div>
        </div>
        <p className="mt-2.5 truncate border-t border-white/10 pt-2 text-[11px] text-white/45">{readings.account}</p>
      </Link>

      <Label>Workspace</Label>
      <Dock items={pinned} pathname={pathname} />

      <Label>Account</Label>
      <nav className="relative flex flex-col">
        {/* A bar of light that slides to where you are. */}
        <span
          aria-hidden
          className={`pointer-events-none absolute inset-x-0 top-0 z-0 h-9 rounded-xl bg-gradient-to-r from-white/[0.2] to-white/[0.04] transition-[transform,opacity] duration-500 ${SPRING}`}
          style={{ transform: `translateY(${beam.index * ROW_REM}rem)`, opacity: beam.visible ? 1 : 0 }}
        >
          <span className="absolute bottom-2 left-0 top-2 w-[3px] rounded-full bg-white shadow-[0_0_10px_1px_rgb(255_255_255/0.8)]" />
        </span>
        {account.map(({ to, label, icon: Icon, count, hot }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `relative z-10 flex h-9 items-center gap-3 rounded-xl pl-3.5 pr-2.5 text-[13.5px] font-semibold transition-colors duration-300 ${
                isActive ? 'text-white' : 'text-white/55 hover:bg-white/[0.04] hover:text-white'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={16} className={isActive ? 'text-white' : ''} />
                <span className="flex-1">{label}</span>
                {count > 0 && (
                  <span
                    className={`rounded-full px-1.5 font-mono text-[11px] font-bold tabular-nums ${
                      hot ? 'bg-coral-400 text-white shadow-[0_0_10px_rgb(247_130_125/0.6)]' : 'text-white/40'
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

      <div className="mt-auto space-y-2.5 pt-5">
        {costs && <BudgetMeter costs={costs} />}

        <div className="deck-well relative grid grid-cols-2 gap-1 rounded-2xl p-1.5">
          <span
            aria-hidden
            className={`absolute inset-y-1.5 left-1.5 z-0 w-[calc(50%-0.5rem)] rounded-xl bg-white shadow-[0_4px_14px_-4px_rgb(0_0_0/0.5)] transition-transform duration-500 ${SPRING}`}
            style={{ transform: emergency ? 'translateX(calc(100% + 0.25rem))' : 'none' }}
          />
          <SpaceButton active={!emergency} dot="bg-arc-300" label="Watching" onClick={() => emergency && onEmergency()} />
          <SpaceButton active={emergency} dot="bg-coral-300" label="Emergency" icon={Flame} onClick={onEmergency} />
        </div>
      </div>
    </>
  )
}

/* The six workspaces as a dock: the icon under the pointer swells and lifts, its neighbours a little,
   and the page you're on carries a glowing dot — like the macOS dock's running indicator. */
function Dock({ items, pathname }) {
  const [hover, setHover] = useState(null)
  return (
    <div className="deck-well relative flex items-end justify-around rounded-2xl px-1.5 pb-3 pt-2.5" onMouseLeave={() => setHover(null)}>
      {items.map((item, i) => {
        const active = isActivePath(item, pathname)
        const distance = hover == null ? Infinity : Math.abs(i - hover)
        const scale = distance === 0 ? 1.32 : distance === 1 ? 1.12 : 1
        const lift = distance === 0 ? -7 : distance === 1 ? -2 : 0
        const Icon = item.icon
        return (
          <div key={item.to} className={`relative ${distance === 0 ? 'z-10' : ''}`}>
            <NavLink
              to={item.to}
              end={item.end}
              aria-label={item.value ? `${item.label}, ${item.value}` : item.label}
              onMouseEnter={() => setHover(i)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
              style={{ transform: `translateY(${lift}px) scale(${scale})` }}
              className={`relative grid h-8 w-8 origin-bottom place-items-center rounded-[0.7rem] transition-[transform,background-color,color] duration-200 ease-out ${
                active
                  ? 'bg-white text-arc-600 shadow-[0_8px_18px_-6px_rgb(10_8_60/0.6)]'
                  : 'text-white/60 hover:bg-white/[0.08] hover:text-white'
              }`}
            >
              <Icon size={16} strokeWidth={2.1} />
              {item.dot > 0 && (
                <span className="absolute -right-1 -top-1 grid h-3.5 min-w-3.5 place-items-center rounded-full bg-coral-400 px-0.5 text-[8.5px] font-bold text-white ring-2 ring-[#3d3ff7]">
                  {item.dot}
                </span>
              )}
              {!item.dot && item.hot && <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-coral-400 ring-2 ring-[#3d3ff7]" />}
            </NavLink>
            {active && (
              <span className="absolute -bottom-2 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-white shadow-[0_0_8px_2px_rgb(255_255_255/0.75)]" />
            )}
            {distance === 0 && (
              <span className="pointer-events-none absolute bottom-[calc(100%+14px)] left-1/2 -translate-x-1/2 whitespace-nowrap rounded-lg bg-white px-2 py-1 text-[11px] font-bold text-ink shadow-[0_8px_20px_-6px_rgb(0_0_0/0.6)]">
                {item.label}
                {item.value && <span className="ml-1.5 font-semibold text-slate-400">{item.value}</span>}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

/* ── Folded ───────────────────────────────────────────────────────────────── */

function Rail({ emergency, onEmergency, pinned, account, pathname, costs, readings, onUnfold, onAsk }) {
  return (
    <>
      <ShieldToggle emergency={emergency} expanded={false} onClick={onUnfold} />

      <button
        type="button"
        onClick={onAsk}
        aria-label={`Ask Ward (${isMac ? '⌘K' : 'Ctrl K'})`}
        className="deck-well mt-4 grid h-10 w-10 shrink-0 place-items-center rounded-2xl text-white transition hover:scale-105"
      >
        <MessageSquareText size={16} />
      </button>

      <span className="my-3 h-px w-7 shrink-0 bg-white/10" />

      <div className="flex flex-col gap-1.5">
        {pinned.map((item) => (
          <RailLink key={item.to} item={item} active={isActivePath(item, pathname)} size="h-10 w-10 rounded-2xl" />
        ))}
      </div>

      <span className="my-3 h-px w-7 shrink-0 bg-white/10" />

      <div className="flex flex-col gap-1">
        {account.map((item) => (
          <RailLink key={item.to} item={item} active={isActivePath(item, pathname)} size="h-9 w-10 rounded-xl" />
        ))}
      </div>

      <div className="min-h-4 flex-1" />

      {costs && <RailGauge costs={costs} />}

      <button
        type="button"
        onClick={onEmergency}
        aria-label={emergency ? 'Emergency mode — review' : 'Watching — switch to Emergency'}
        className={`mt-3 grid h-10 w-10 shrink-0 place-items-center rounded-2xl transition hover:scale-105 ${
          emergency ? 'bg-white text-coral-500' : 'deck-well text-white/70'
        }`}
      >
        {emergency ? <Flame size={16} /> : <Eye size={16} />}
      </button>

      <Link to="/connect" aria-label={`${readings.account} — ${readings.tag}`} className="mt-3 grid h-6 w-6 place-items-center rounded-full hover:bg-white/10">
        <span className={`h-2 w-2 rounded-full ${readings.tone}`} />
      </Link>
    </>
  )
}

function RailLink({ item, active, size }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      end={item.end}
      aria-label={item.label}
      className={`relative grid place-items-center transition duration-300 ${size} ${
        active
          ? 'bg-white text-arc-600 shadow-[0_8px_18px_-6px_rgb(10_8_60/0.6)]'
          : 'text-white/60 hover:scale-105 hover:bg-white/[0.07] hover:text-white'
      }`}
    >
      <Icon size={16} strokeWidth={2.1} />
      {(item.dot > 0 || item.count > 0) && (
        <span
          className={`absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full px-1 text-[9px] font-bold ring-2 ring-[#3d3ff7] ${
            item.dot > 0 || item.hot ? 'bg-coral-400 text-white' : 'bg-white/90 text-arc-700'
          }`}
        >
          {item.dot || item.count}
        </span>
      )}
      {!item.dot && !item.count && item.hot && <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-coral-400 ring-2 ring-[#3d3ff7]" />}
    </NavLink>
  )
}

/* ── Pieces ───────────────────────────────────────────────────────────────── */

function Label({ children }) {
  return <p className="mb-2 mt-5 px-1 text-[10px] font-bold uppercase tracking-[0.18em] text-white/35">{children}</p>
}

// The shield doubles as the fold control.
function ShieldToggle({ emergency, expanded, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={expanded ? 'Fold the sidebar' : 'Unfold the sidebar'}
      aria-expanded={expanded}
      title={`${expanded ? 'Fold' : 'Unfold'} · [`}
      className="group grid h-9 w-9 shrink-0 place-items-center rounded-full"
    >
      <span className="transition-transform duration-300 group-hover:scale-110 group-active:scale-95">
        <WardMark emergency={emergency} />
      </span>
    </button>
  )
}

const SEGMENTS = 20

// The month at a glance, as a segmented meter that lights up — one segment per 5% of the budget,
// with an outline on the segment where the current burn rate says the month will land.
function BudgetMeter({ costs }) {
  const { spentPct, projectedPct, over, daysLeft } = budget(costs)
  const lit = Math.round((Math.min(spentPct, 100) / 100) * SEGMENTS)
  const landing = projectedPct > 0 ? Math.min(SEGMENTS - 1, Math.floor((Math.min(projectedPct, 100) / 100) * SEGMENTS)) : -1
  return (
    <div className="deck-well rounded-2xl px-3.5 py-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-white/50">Month to date</span>
        <span className="font-display text-[15px] font-semibold">{rupeesShort(costs.monthToDate)}</span>
      </div>
      <div className="mt-2.5 flex gap-[3px]" aria-label={`${spentPct}% of the monthly budget spent`}>
        {Array.from({ length: SEGMENTS }, (_, i) => (
          <span
            key={i}
            className={`h-2.5 flex-1 rounded-[2px] transition-colors duration-500 ${
              i < lit
                ? over ? 'bg-coral-300 shadow-[0_0_6px_rgb(252_165_160/0.7)]' : 'bg-white shadow-[0_0_6px_rgb(255_255_255/0.6)]'
                : 'bg-white/10'
            } ${i === landing ? 'outline outline-1 outline-offset-1 outline-white/60' : ''}`}
          />
        ))}
      </div>
      <p className="mt-2 text-[10.5px] font-semibold text-white/45">
        {spentPct}% of {rupeesShort(costs.budget)} · {over ? `tracking ${projectedPct}%` : `${daysLeft}d left`}
      </p>
    </div>
  )
}

// The same meter stood on end for the rail: it fills upward.
function RailGauge({ costs }) {
  const { spentPct, projectedPct, over } = budget(costs)
  const n = 12
  const lit = Math.round((Math.min(spentPct, 100) / 100) * n)
  return (
    <Link
      to="/app"
      aria-label={`Month to date ${rupeesShort(costs.monthToDate)}, ${spentPct}% of budget, projected ${projectedPct}%`}
      className="flex flex-col items-center gap-2 rounded-xl px-2 py-1.5 transition hover:bg-white/[0.06]"
    >
      <div className="flex flex-col-reverse gap-[3px]">
        {Array.from({ length: n }, (_, i) => (
          <span
            key={i}
            className={`h-1.5 w-3 rounded-[2px] ${i < lit ? (over ? 'bg-coral-300' : 'bg-white') : 'bg-white/10'}`}
          />
        ))}
      </div>
      <span className="text-[9.5px] font-bold tabular-nums text-white/70">{rupeesShort(costs.monthToDate)}</span>
    </Link>
  )
}

function SpaceButton({ active, dot, label, icon: Icon, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`relative z-10 flex items-center justify-center gap-1.5 rounded-xl px-2 py-2 text-xs font-bold transition-colors duration-300 ${
        active ? 'text-ink' : 'text-white/55 hover:text-white'
      }`}
    >
      {Icon && active ? <Icon size={13} className="text-coral-500" /> : <span className={`h-2 w-2 rounded-full ${dot} ring-2 ring-white/20`} />}
      {label}
    </button>
  )
}

function budget(costs) {
  const spentPct = Math.round((costs.monthToDate / costs.budget) * 100)
  const projectedPct = Math.round((costs.projectedMonthEnd / costs.budget) * 100)
  const now = new Date()
  const daysLeft = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate() - now.getDate()
  return { spentPct, projectedPct, over: projectedPct > 100, daysLeft }
}

// A sliding highlight keeps its last position when you leave its group, fading out rather than
// flying back to the first item — and fades in at the new spot when you return.
function useSticky(index) {
  const last = useRef(Math.max(index, 0))
  if (index >= 0) last.current = index
  return { index: last.current, visible: index >= 0 }
}
