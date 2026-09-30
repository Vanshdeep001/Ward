import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, Bell, BellOff, Cpu, Database, Globe2, HardDrive, ShieldAlert, Tag, Timer } from 'lucide-react'
import { useAlerts, useRules, useSnooze } from '../api/hooks.js'
import { ago, rupees } from '../lib/format.js'
import { Aura, ErrorState, Loading } from '../components/ui.jsx'

/* Alerts as cases, not rows. Eight alerts from two rules are two problems, so the page is organised by
   rule: each broken rule is a card led by how many resources break it, with those resources laid out
   as tiles of plain facts — how long it's been up, what it costs, how long it's been open. The alert
   message was prose written when it fired; everything here is structured, from the live inventory. */

const FAMILY = {
  'ec2-runtime': { icon: Timer, label: 'Runtime limit' },
  'require-tag': { icon: Tag, label: 'Tagging' },
  'ebs-unattached': { icon: HardDrive, label: 'Idle storage' },
  'rds-public': { icon: Database, label: 'Exposure' },
  'sg-open-port': { icon: ShieldAlert, label: 'Network exposure' },
  'instance-type': { icon: Cpu, label: 'Instance types' },
  region: { icon: Globe2, label: 'Region' },
}

const TABS = [
  { key: 'open', label: 'Open' },
  { key: 'snoozed', label: 'Snoozed' },
  { key: 'resolved', label: 'Resolved' },
]

const TONE = {
  alert: { number: 'text-coral-600', label: 'text-coral-600', dot: 'bg-coral-500', aura: 'coral' },
  warning: { number: 'text-amber-600', label: 'text-amber-700', dot: 'bg-amber-400', aura: 'amber' },
  snoozed: { number: 'text-violet-600', label: 'text-violet-700', dot: 'bg-violet-400', aura: 'lilac' },
  resolved: { number: 'text-emerald-600', label: 'text-emerald-700', dot: 'bg-emerald-500', aura: 'green' },
}

export default function Alerts() {
  const { data: alerts, isLoading, error, refetch } = useAlerts()
  const { data: rules } = useRules()
  const snooze = useSnooze()
  const [tab, setTab] = useState('open')

  if (isLoading) return <Loading label="Gathering your alerts…" />
  if (!alerts) return <ErrorState error={error} onRetry={() => refetch()} />

  const by = { open: [], snoozed: [], resolved: [] }
  for (const a of alerts ?? []) by[a.status]?.push(a)
  const kindOf = Object.fromEntries((rules ?? []).map((r) => [r.id, r.intent?.kind]))
  const cases = groupByRule(by[tab], kindOf, tab)

  return (
    <>
      <Hero open={by.open} counts={{ snoozed: by.snoozed.length, resolved: by.resolved.length }} />

      <Tabs tab={tab} onChange={setTab} counts={{ open: by.open.length, snoozed: by.snoozed.length, resolved: by.resolved.length }} />

      {cases.length ? (
        <div className="mt-6 space-y-6">
          {cases.map((c) => (
            <Case key={c.ruleId} c={c} tab={tab} snooze={snooze} />
          ))}
        </div>
      ) : (
        <Empty tab={tab} />
      )}

      <p className="mt-8 flex items-start gap-2 text-[12.5px] leading-relaxed text-slate-500">
        <BellOff size={14} className="mt-0.5 shrink-0" />
        Snoozing tells Ward a resource is intentional. It stays silent until the timer runs out, then judges it afresh —
        so a resource that is still breaking the rule speaks up again.
      </p>
    </>
  )
}

/* ── The headline ─────────────────────────────────────────────────────────── */

function Hero({ open, counts }) {
  const resources = new Set(open.map((a) => a.resourceId)).size
  const rules = new Set(open.map((a) => a.ruleId)).size
  const atStake = sumDistinct(open)

  return (
    <header className="mb-10 grid gap-8 lg:grid-cols-[1fr_auto] lg:items-end">
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400">Alerts · state changes only, never every poll</p>
        <h1 className="mt-4 max-w-3xl font-display text-[clamp(2.2rem,5vw,3.6rem)] font-semibold leading-[1.02] tracking-tight text-ink">
          {resources ? (
            <>
              <span className="text-coral-600">{resources}</span> resource{resources === 1 ? ' is' : 's are'} breaking{' '}
              <span className="text-arc-600">{rules}</span> of your rules.
            </>
          ) : (
            'Nothing is breaking your rules right now.'
          )}
        </h1>
        {atStake > 0 && (
          <p className="mt-4 text-[15px] text-slate-600">
            Together they cost <span className="font-semibold text-ink">{rupees(atStake)} a day</span> while they stay this way —{' '}
            {rupees(atStake * 30)} over a month.
          </p>
        )}
      </div>

      <dl className="flex gap-8 lg:gap-10">
        <Readout label="Open" value={open.length} tone={TONE.alert} />
        <Readout label="Snoozed" value={counts.snoozed} tone={TONE.snoozed} />
        <Readout label="Resolved" value={counts.resolved} tone={TONE.resolved} />
      </dl>
    </header>
  )
}

function Readout({ label, value, tone }) {
  return (
    <div>
      <dt className="flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-[0.16em] text-slate-400">
        <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} /> {label}
      </dt>
      <dd className={`mt-1.5 font-display text-[2.6rem] font-semibold leading-none ${value ? tone.number : 'text-slate-300'}`}>{value}</dd>
    </div>
  )
}

/* ── Tabs, with a pill that slides ───────────────────────────────────────── */

function Tabs({ tab, onChange, counts }) {
  const index = TABS.findIndex((t) => t.key === tab)
  return (
    <div className="relative grid w-full max-w-md grid-cols-3 rounded-2xl border border-slate-200/80 bg-white p-1 shadow-[0_1px_2px_rgb(15_23_42/0.04)]">
      <span
        aria-hidden
        className="absolute inset-y-1 left-1 w-[calc((100%-0.5rem)/3)] rounded-xl bg-ink shadow-[0_6px_16px_-8px_rgb(0_0_0/0.5)] transition-transform duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]"
        style={{ transform: `translateX(${index * 100}%)` }}
      />
      {TABS.map((t) => (
        <button
          key={t.key}
          type="button"
          onClick={() => onChange(t.key)}
          aria-pressed={tab === t.key}
          className={`relative z-10 flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-[13px] font-bold transition-colors duration-300 ${
            tab === t.key ? 'text-white' : 'text-slate-500 hover:text-ink'
          }`}
        >
          {t.label}
          <span
            className={`rounded-md px-1.5 text-[11px] tabular-nums transition-colors duration-300 ${
              tab === t.key ? 'bg-white/15 text-white' : 'bg-slate-100 text-slate-500'
            }`}
          >
            {counts[t.key]}
          </span>
        </button>
      ))}
    </div>
  )
}

/* ── One broken rule ──────────────────────────────────────────────────────── */

function Case({ c, tab, snooze }) {
  const family = FAMILY[c.kind] ?? { icon: Bell, label: 'Guardrail' }
  const Icon = family.icon
  const tone = tab === 'open' ? TONE[c.level] : TONE[tab]
  const verb = tab === 'resolved' ? 'Was breaking' : tab === 'snoozed' ? 'Silenced on' : c.level === 'alert' ? 'Breaking' : 'Getting close to'

  async function snoozeAll(hours) {
    for (const a of c.alerts) await snooze.mutateAsync({ id: a.id, hours })
  }

  return (
    <section className="group/aura relative overflow-hidden rounded-3xl border border-slate-200/70 bg-white shadow-[0_1px_2px_rgb(15_23_42/0.04),0_20px_44px_-30px_rgb(23_23_60/0.45)]">
      <header className="grid gap-x-7 gap-y-4 px-6 pb-2 pt-6 md:grid-cols-[auto_1fr_auto] md:items-start md:px-7">
        {/* The count is the anchor: how many things this one rule is catching. */}
        <div className="flex items-baseline gap-2 md:block">
          <p className={`font-display text-[3.6rem] font-semibold leading-[0.8] ${tone.number}`}>{c.alerts.length}</p>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400 md:mt-2">
            resource{c.alerts.length === 1 ? '' : 's'}
          </p>
        </div>

        <div className="min-w-0">
          <p className={`flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-[0.16em] ${tone.label}`}>
            <Icon size={13} /> {verb} · {family.label}
          </p>
          <h2 className="mt-2 font-display text-[clamp(1.35rem,2.4vw,1.85rem)] font-semibold leading-[1.15] tracking-tight text-ink">
            “{c.rule}”
          </h2>
          <p className="mt-2 text-[13px] text-slate-500">
            {tab === 'resolved' ? `Last resolved ${ago(c.latestResolved)}` : `First broke ${ago(c.oldest)}`}
            {' · '}
            {c.costPerDay > 0 ? (
              <span className="font-semibold text-ink">{rupees(c.costPerDay)}/day at stake</span>
            ) : (
              'no running cost — this is a hygiene rule'
            )}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 md:justify-end">
          {tab === 'open' && c.alerts.length > 1 && (
            <SnoozeChoice label="Snooze all" onSnooze={snoozeAll} busy={snooze.isPending} />
          )}
          <Link
            to="/rules"
            className="inline-flex items-center gap-1 rounded-full border border-slate-200 px-3 py-1.5 text-[12px] font-bold text-slate-600 transition hover:border-arc-200 hover:bg-arc-50 hover:text-arc-700"
          >
            Rule <ArrowUpRight size={13} />
          </Link>
        </div>
      </header>

      <div className="grid gap-3 px-6 pb-6 pt-4 sm:grid-cols-2 md:px-7 xl:grid-cols-3">
        {c.alerts.map((a) => (
          <ResourceTile key={a.id} a={a} tab={tab} snooze={snooze} aura={tone.aura} />
        ))}
      </div>
      <Aura color={tone.aura} icon={Icon} size={160} />
    </section>
  )
}

function ResourceTile({ a, tab, snooze, aura }) {
  const r = a.resource
  return (
    <article className="group group/aura relative flex flex-col overflow-hidden rounded-2xl border border-slate-200/80 bg-paper/70 p-4 transition duration-300 hover:-translate-y-0.5 hover:border-slate-300 hover:bg-white hover:shadow-[0_14px_30px_-18px_rgb(23_23_60/0.45)]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[15.5px] font-semibold text-ink">{r.name || r.id}</p>
          <p className="mt-0.5 truncate font-mono text-[11px] text-slate-400">
            {r.id}
            {r.region && ` · ${r.region}`}
          </p>
        </div>
        {r.detail && (
          <span className="shrink-0 rounded-lg bg-white px-2 py-1 font-mono text-[11px] font-semibold text-slate-600 ring-1 ring-inset ring-slate-200">
            {r.detail}
          </span>
        )}
      </div>

      <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-slate-200/70 pt-3">
        <Fact label="Up for" value={r.runningHours ? span(r.runningHours) : '—'} />
        <Fact label="Costs" value={r.costPerDay ? `${rupees(r.costPerDay)}/d` : 'nothing'} muted={!r.costPerDay} />
        {tab === 'resolved' ? (
          <Fact label="Resolved" value={a.resolvedAt ? ago(a.resolvedAt) : '—'} />
        ) : (
          <Fact label="Open for" value={span((Date.now() - new Date(a.at).getTime()) / 3_600_000)} />
        )}
      </dl>

      {r.present === false && (
        <p className="mt-3 text-[11.5px] text-slate-400">No longer in the inventory — it was stopped or deleted.</p>
      )}

      <div className="mt-auto pt-3">
        {tab === 'open' && <SnoozeChoice label="Intentional?" onSnooze={(hours) => snooze.mutate({ id: a.id, hours })} busy={snooze.isPending} quiet />}
        {tab === 'snoozed' && a.snoozedUntil && (
          <p className="flex items-center gap-1.5 text-[12px] font-semibold text-violet-700">
            <BellOff size={13} /> Silent — wakes in {span((new Date(a.snoozedUntil).getTime() - Date.now()) / 3_600_000)}
          </p>
        )}
      </div>
      <Aura color={aura} />
    </article>
  )
}

function Fact({ label, value, muted }) {
  return (
    <div className="min-w-0">
      <dt className="text-[9.5px] font-bold uppercase tracking-[0.14em] text-slate-400">{label}</dt>
      <dd className={`mt-0.5 truncate text-[14px] font-semibold tabular-nums ${muted ? 'text-slate-400' : 'text-ink'}`}>{value}</dd>
    </div>
  )
}

function SnoozeChoice({ label, onSnooze, busy, quiet }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={`mr-auto text-[11.5px] ${quiet ? 'text-slate-400' : 'font-semibold text-slate-500'}`}>{label}</span>
      {[4, 24].map((h) => (
        <button
          key={h}
          type="button"
          onClick={() => onSnooze(h)}
          disabled={busy}
          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11.5px] font-bold text-slate-600 transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 disabled:opacity-50"
        >
          <BellOff size={11} /> {h}h
        </button>
      ))}
    </div>
  )
}

function Empty({ tab }) {
  const copy = {
    open: ['All clear.', 'Nothing is breaking a guardrail. Ward keeps checking every 15 minutes.'],
    snoozed: ['Nothing snoozed.', 'Snoozed alerts appear here, with how long until Ward looks again.'],
    resolved: ['Nothing resolved yet.', 'When a resource stops breaking a rule, the alert closes and lands here.'],
  }[tab]
  return (
    <div className="mt-6 rounded-3xl border border-dashed border-slate-300 px-6 py-16 text-center">
      <p className="font-display text-[2rem] font-semibold text-ink">{copy[0]}</p>
      <p className="mx-auto mt-2 max-w-md text-[14px] text-slate-500">{copy[1]}</p>
    </div>
  )
}

/* ── Shaping the data ─────────────────────────────────────────────────────── */

// One case per rule. In the resolved tab a resource can have closed several times; show its latest.
function groupByRule(alerts, kindOf, tab) {
  const cases = new Map()
  for (const a of alerts) {
    const c = cases.get(a.ruleId) ?? { ruleId: a.ruleId, rule: a.rule.english, kind: kindOf[a.ruleId], level: 'warning', alerts: [] }
    if (a.level === 'alert') c.level = 'alert'
    if (tab !== 'resolved' || !c.alerts.some((x) => x.resourceId === a.resourceId)) c.alerts.push(a)
    cases.set(a.ruleId, c)
  }
  return [...cases.values()]
    .map((c) => ({
      ...c,
      oldest: c.alerts.reduce((m, a) => (a.at < m ? a.at : m), c.alerts[0].at),
      latestResolved: c.alerts.reduce((m, a) => (a.resolvedAt && a.resolvedAt > m ? a.resolvedAt : m), ''),
      costPerDay: sumDistinct(c.alerts),
    }))
    .sort((x, y) => y.alerts.length - x.alerts.length || y.costPerDay - x.costPerDay)
}

// A resource breaking two rules costs what it costs once.
function sumDistinct(alerts) {
  const seen = new Map()
  for (const a of alerts) seen.set(a.resourceId, a.resource?.costPerDay ?? (a.projectedMonthly ?? 0) / 30)
  return [...seen.values()].reduce((s, v) => s + (v || 0), 0)
}

// Hours as a person would say them: 45m, 9h, 86 days, 3 months.
function span(hours) {
  if (hours == null || Number.isNaN(hours) || hours < 0) return '—'
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m`
  if (hours < 48) return `${Math.round(hours)}h`
  if (hours < 24 * 60) return `${Math.round(hours / 24)} days`
  return `${Math.round(hours / 24 / 30)} months`
}
