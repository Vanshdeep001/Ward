import { Fragment, useMemo, useState } from 'react'
import { Boxes, Database, HardDrive, Network, Package, Server, ShieldCheck, UserX } from 'lucide-react'
import { useResources } from '../api/hooks.js'
import { ago, rupees } from '../lib/format.js'
import { Aura, Loading } from '../components/ui.jsx'
import StateBadge from '../components/StateBadge.jsx'

/* The inventory as a map, not a spreadsheet. The headline says what Ward sees and what it costs, a
   single band shows what the account is made of, and each service gets its own shelf of tiles — plain
   facts per resource, with the things worth noticing (no owner, far-away region, idle) called out. */

const HOME_REGION = 'ap-south-1'

const KIND = {
  ec2: { icon: Server, label: 'Instances', one: 'instance', color: '#3139fb' },
  rds: { icon: Database, label: 'Databases', one: 'database', color: '#b79bff' },
  ebs: { icon: HardDrive, label: 'Volumes', one: 'volume', color: '#8e96ff' },
  nat: { icon: Network, label: 'Nat Gateways', one: 'NAT gateway', color: '#ffb48f' },
  s3: { icon: Package, label: 'Buckets', one: 'bucket', color: '#f5a3c7' },
  sg: { icon: ShieldCheck, label: 'Security Groups', one: 'security group', color: '#f7827d' },
}
const ORDER = Object.keys(KIND)

export default function Resources() {
  const { data, isLoading } = useResources()
  const [type, setType] = useState('all')
  const [ownerless, setOwnerless] = useState(false)

  const all = data?.items ?? []
  const counts = useMemo(() => countBy(all), [all])
  const shelves = useMemo(() => {
    const shown = all.filter((r) => (type === 'all' || r.type === type) && (!ownerless || !r.tags.Owner))
    return ORDER.map((t) => ({ type: t, items: sortForShelf(shown.filter((r) => r.type === t)) })).filter((s) => s.items.length)
  }, [all, type, ownerless])

  if (isLoading) return <Loading />

  return (
    <>
      <Hero items={all} counts={counts} asOf={data.asOf} />

      <div className="mt-10 flex flex-wrap items-center gap-3">
        <TypeTabs value={type} onChange={setType} counts={counts} total={all.length} />
        <button
          type="button"
          onClick={() => setOwnerless((v) => !v)}
          aria-pressed={ownerless}
          className={`inline-flex items-center gap-2 rounded-2xl border px-3.5 py-2.5 text-[13px] font-bold transition ${
            ownerless ? 'border-coral-300 bg-coral-50 text-coral-600' : 'border-slate-200/80 bg-white text-slate-500 hover:text-ink'
          }`}
        >
          <UserX size={15} /> <Initials text="No owner only" />
        </button>
      </div>

      {shelves.length ? (
        <div className="mt-8 space-y-10">
          {shelves.map((s) => <Shelf key={s.type} type={s.type} items={s.items} />)}
        </div>
      ) : (
        <div className="mt-8 rounded-3xl border border-dashed border-slate-300 px-6 py-16 text-center">
          <p className="font-display text-[2rem] font-medium text-ink"><Initials text="Nothing matches." /></p>
          <p className="mx-auto mt-2 max-w-md text-[14px] text-slate-500">Try another service, or turn off the owner filter.</p>
        </div>
      )}
    </>
  )
}

/* ── The headline ─────────────────────────────────────────────────────────── */

function Hero({ items, counts, asOf }) {
  const paying = items.filter((r) => r.costPerHour > 0)
  const perDay = paying.reduce((s, r) => s + r.costPerHour * 24, 0)
  const running = items.filter((r) => r.running).length
  const noOwner = items.filter((r) => !r.tags.Owner).length
  const away = items.filter((r) => r.region && r.region !== HOME_REGION).length

  return (
    <header>
      <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400">Resources · inventory as of {ago(asOf)}</p>

      <div className="mt-4 grid gap-8 lg:grid-cols-[1fr_auto] lg:items-end">
        <h1 className="max-w-3xl font-display text-[clamp(2.2rem,5vw,3.6rem)] font-medium leading-[1.04] tracking-tight text-ink">
          <Initials text="Ward can see" /> <Num className="text-arc-600">{items.length}</Num> <Initials text="resources." />{' '}
          {paying.length ? (
            <>
              <Num className="text-coral-600">{paying.length}</Num> <Initials text={`of them cost you ${rupees(perDay)} a day.`} />
            </>
          ) : (
            <Initials text="None of them cost anything right now." />
          )}
        </h1>

        <dl className="flex gap-8 lg:gap-10">
          <Readout label="Running" value={running} dot="bg-emerald-500" tone="text-emerald-600" />
          <Readout label="No owner" value={noOwner} dot="bg-coral-500" tone="text-coral-600" />
          <Readout label="Off region" value={away} dot="bg-amber-400" tone="text-amber-600" />
        </dl>
      </div>

      <Makeup counts={counts} total={items.length} />
    </header>
  )
}

// What the account is made of: one band, a segment per service, sized by how many there are.
function Makeup({ counts, total }) {
  const parts = ORDER.filter((t) => counts[t])
  if (!total) return null
  return (
    <div className="mt-8">
      <div className="flex h-4 gap-1 overflow-hidden rounded-full">
        {parts.map((t, i) => (
          <span
            key={t}
            className="h-full origin-left rounded-full"
            style={{ flexGrow: counts[t], background: KIND[t].color, animation: `grow-x 0.8s cubic-bezier(0.32,0.72,0,1) ${i * 90}ms both` }}
          />
        ))}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-6 gap-y-2">
        {parts.map((t) => (
          <li key={t} className="flex items-center gap-2 text-[13px] text-slate-600">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: KIND[t].color }} />
            <Initials text={KIND[t].label} />
            <span className="font-semibold tabular-nums text-ink">{counts[t]}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Readout({ label, value, dot, tone }) {
  return (
    <div>
      <dt className="flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-[0.16em] text-slate-400">
        <span className={`h-1.5 w-1.5 rounded-full ${dot}`} /> {label}
      </dt>
      <dd className={`mt-1.5 font-display text-[2.6rem] font-semibold leading-none ${value ? tone : 'text-slate-300'}`}>{value}</dd>
    </div>
  )
}

/* ── Service tabs, with a pill that slides ───────────────────────────────── */

function TypeTabs({ value, onChange, counts, total }) {
  const tabs = [{ key: 'all', label: 'All', n: total }, ...ORDER.filter((t) => counts[t]).map((t) => ({ key: t, label: KIND[t].label, n: counts[t] }))]
  return (
    <div className="flex flex-wrap gap-1 rounded-2xl border border-slate-200/80 bg-white p-1 shadow-[0_1px_2px_rgb(15_23_42/0.04)]">
      {tabs.map((t) => {
        const on = value === t.key
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            aria-pressed={on}
            className={`flex items-center gap-2 rounded-xl px-3 py-1.5 text-[13px] transition-colors duration-300 ${
              on ? 'bg-ink text-white shadow-[0_6px_16px_-8px_rgb(0_0_0/0.5)]' : 'text-slate-500 hover:text-ink'
            }`}
          >
            {t.key !== 'all' && <span className="h-2 w-2 rounded-full" style={{ background: KIND[t.key].color }} />}
            <Initials text={t.label} />
            <span className={`rounded-md px-1.5 text-[11px] font-bold tabular-nums ${on ? 'bg-white/15 text-white' : 'bg-slate-100 text-slate-500'}`}>{t.n}</span>
          </button>
        )
      })}
    </div>
  )
}

/* ── One service ─────────────────────────────────────────────────────────── */

function Shelf({ type, items }) {
  const kind = KIND[type]
  const Icon = kind.icon ?? Boxes
  const perDay = items.reduce((s, r) => s + r.costPerHour * 24, 0)

  return (
    <section>
      <header className="mb-4 flex items-end gap-4">
        <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl text-white shadow-[0_10px_22px_-12px_rgb(23_23_60/0.6)]" style={{ background: kind.color }}>
          <Icon size={22} strokeWidth={2.2} />
        </span>
        <div className="min-w-0">
          <h2 className="font-display text-[1.75rem] font-medium leading-none tracking-tight text-ink">
            <Initials text={kind.label} /> <span className="font-semibold text-slate-300">{items.length}</span>
          </h2>
          <p className="mt-1.5 text-[13px] text-slate-500">
            {perDay > 0 ? <><span className="font-semibold text-ink">{rupees(perDay)}</span> a day between them</> : 'Nothing to pay for'}
          </p>
        </div>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((r) => <Tile key={r.id} r={r} color={kind.color} icon={Icon} />)}
      </div>
    </section>
  )
}

function Tile({ r, color, icon: Icon }) {
  const owner = r.tags.Owner
  const away = r.region && r.region !== HOME_REGION
  const status = statusOf(r)
  const perDay = r.costPerHour * 24

  return (
    <article className="group/aura relative flex flex-col overflow-hidden rounded-3xl border border-slate-200/70 bg-white p-5 shadow-[0_1px_2px_rgb(15_23_42/0.04),0_20px_44px_-34px_rgb(23_23_60/0.45)] transition duration-300 hover:-translate-y-0.5 hover:shadow-[0_1px_2px_rgb(15_23_42/0.04),0_24px_48px_-26px_rgb(23_23_60/0.5)]">

      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[17px] leading-tight text-ink"><Initials text={r.name} /></p>
          <p className="mt-1 truncate font-mono text-[11px] text-slate-400">{r.id}</p>
        </div>
        {r.instanceType && (
          <span className="shrink-0 rounded-lg bg-arc-50 px-2 py-1 font-mono text-[11px] font-semibold text-arc-700 ring-1 ring-inset ring-arc-100">
            {r.instanceType}
          </span>
        )}
      </div>

      <p className={`mt-3 flex items-center gap-1.5 text-[12px] font-semibold ${status.tone}`}>
        <span className={`h-1.5 w-1.5 rounded-full ${status.dot}`} /> {status.label}
      </p>

      <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-slate-100 pt-3">
        <Fact label="Up for" value={r.running && r.runtimeHours ? span(r.runtimeHours) : '—'} muted={!r.runtimeHours} />
        <Fact label="Costs" value={perDay > 0 ? `${rupees(perDay)}/d` : 'nothing'} muted={!(perDay > 0)} />
        <Fact label="Region" value={r.region ?? 'global'} tone={away ? 'text-amber-600' : undefined} />
      </dl>

      <div className="mt-auto flex items-center justify-between gap-2 pt-4">
        {owner ? (
          <span className="truncate text-[12.5px] text-slate-500">
            Owned by <span className="text-ink"><Initials text={owner} /></span>
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-coral-50 px-2.5 py-1 text-[11.5px] font-bold text-coral-600">
            <UserX size={12} /> No owner
          </span>
        )}
        {r.state !== 'discovered' && <StateBadge state={r.state} />}
      </div>
      <Aura color={color} icon={Icon} />
    </article>
  )
}

function Fact({ label, value, muted, tone }) {
  return (
    <div className="min-w-0">
      <dt className="text-[9.5px] font-bold uppercase tracking-[0.14em] text-slate-400">{label}</dt>
      <dd className={`mt-0.5 truncate text-[14px] font-semibold tabular-nums ${tone ?? (muted ? 'text-slate-400' : 'text-ink')}`}>{value}</dd>
    </div>
  )
}

/* ── Type ─────────────────────────────────────────────────────────────────── */

// Every word's first letter heavy, the rest light. Words split on spaces, hyphens, underscores and dots,
// so "launch-wizard-1" reads as three words.
function Initials({ text }) {
  // One wrapping span, so a flex parent with a gap sees a single item rather than spacing every letter apart.
  const parts = String(text ?? '').split(/([\s\-_.:/]+)/)
  return (
    <span>
      {parts.map((p, i) =>
        /^[\s\-_.:/]*$/.test(p) ? (
          <Fragment key={i}>{p}</Fragment>
        ) : (
          <Fragment key={i}>
            <b className="font-extrabold">{p[0]}</b>
            <span className="font-normal">{p.slice(1)}</span>
          </Fragment>
        ),
      )}
    </span>
  )
}

// Numbers in the headline are words too: heavy throughout, in colour.
function Num({ children, className }) {
  return <span className={`font-extrabold ${className}`}>{children}</span>
}

/* ── Shaping the data ─────────────────────────────────────────────────────── */

function countBy(items) {
  const c = {}
  for (const r of items) c[r.type] = (c[r.type] ?? 0) + 1
  return c
}

// Most expensive first, then the ones that need attention, then by name.
function sortForShelf(items) {
  return [...items].sort(
    (a, b) => b.costPerHour - a.costPerHour || Number(!!a.tags.Owner) - Number(!!b.tags.Owner) || a.name.localeCompare(b.name),
  )
}

function statusOf(r) {
  if (r.type === 'ebs') return r.attached ? { label: 'Attached', tone: 'text-emerald-700', dot: 'bg-emerald-500' } : { label: 'Unattached — idle', tone: 'text-amber-700', dot: 'bg-amber-400' }
  if (r.type === 'sg') return { label: 'Firewall rules', tone: 'text-slate-500', dot: 'bg-slate-300' }
  if (r.type === 's3') return { label: 'Stored', tone: 'text-slate-500', dot: 'bg-slate-300' }
  return r.running ? { label: 'Running', tone: 'text-emerald-700', dot: 'bg-emerald-500' } : { label: 'Stopped', tone: 'text-slate-500', dot: 'bg-slate-300' }
}

// Hours as a person would say them: 45m, 9h, 86 days, 3 months.
function span(hours) {
  if (hours == null || Number.isNaN(hours) || hours < 0) return '—'
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m`
  if (hours < 48) return `${Math.round(hours)}h`
  if (hours < 24 * 60) return `${Math.round(hours / 24)} days`
  return `${Math.round(hours / 24 / 30)} months`
}
