import { Link } from 'react-router-dom'
import { ArrowRight, ShieldAlert } from 'lucide-react'
import { rupees, rupeesShort } from '../lib/format.js'
import { Panel, PanelLink } from './ui.jsx'

/* What is breaking the rules right now, as three readings instead of a list of sentences:
   the money exposed, when the alerts landed over 30 days, and which resources carry it.

   Twelve alerts are usually not twelve problems — the same instance breaks several rules at once.
   Grouping by resource is what makes the number honest: a resource's cost is counted once, however
   many rules it trips. */

const DAYS = 30
const SHOWN = 5 // the long cheap tail folds into one row, so the panel stays about the ones that matter

export default function RiskBoard({ alerts = [], isLoading }) {
  const open = alerts.filter((a) => a.status === 'open')
  const byResource = groupByResource(open)
  const atRisk = byResource.reduce((sum, r) => sum + r.costPerDay, 0)
  const worst = byResource[0]?.costPerDay || 1
  const shown = byResource.slice(0, SHOWN)
  const tail = byResource.slice(SHOWN)
  const tailCost = tail.reduce((sum, r) => sum + r.costPerDay, 0)
  const history = dailyCounts(alerts)
  const peak = Math.max(...history.map((d) => d.count), 1)

  return (
    <Panel
      className="lg:col-span-2"
      eyebrow={`${open.length} open · ${byResource.length} resource${byResource.length === 1 ? '' : 's'} · ${alerts.length} in 30 days`}
      title="Live exposure"
      action={<PanelLink to="/alerts">All alerts</PanelLink>}
    >
      {/* The hero reading: what the open alerts are costing while they stay open. */}
      <div className={`border-b border-slate-100 px-5 pb-5 pt-4 ${atRisk ? 'bg-gradient-to-b from-coral-50/70 to-transparent' : 'bg-gradient-to-b from-emerald-50/60 to-transparent'}`}>
        <p className={`text-[10px] font-bold uppercase tracking-[0.14em] ${atRisk ? 'text-coral-600/80' : 'text-emerald-700/70'}`}>
          Breaking your rules right now
        </p>
        <p className={`mt-1 font-display text-[2.6rem] font-semibold leading-none ${atRisk ? 'text-coral-600' : 'text-emerald-700'}`}>
          {atRisk ? `${rupees(atRisk)}/day` : 'All clear'}
        </p>
        <p className="mt-2 text-[11.5px] font-medium text-slate-500">
          {atRisk
            ? `${rupees(atRisk * 30)} a month if nothing changes · counted once per resource`
            : 'Nothing in your account is breaking a guardrail.'}
        </p>
      </div>

      {/* Thirty days of alert volume — one cell a day, so a noisy rulebook is visible at a glance. */}
      <div className="border-b border-slate-100 px-5 py-4">
        <div className="flex items-baseline justify-between text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
          <span>Alerts, last 30 days</span>
          <span className="tabular-nums text-slate-500">{alerts.length} total</span>
        </div>
        <div className="mt-2.5 flex gap-[3px]">
          {history.map((day) => (
            <span
              key={day.key}
              title={`${day.label} · ${day.count} alert${day.count === 1 ? '' : 's'}`}
              className={`h-7 flex-1 rounded-[3px] transition ${intensity(day.count, peak)}`}
            />
          ))}
        </div>
        <div className="mt-1.5 flex justify-between text-[10px] font-medium text-slate-400">
          <span>30 days ago</span>
          <span>today</span>
        </div>
      </div>

      {/* Ranked by what each resource costs while it stays in breach. */}
      {isLoading ? (
        <p className="px-5 py-10 text-center text-sm text-slate-400">Loading…</p>
      ) : byResource.length === 0 ? (
        <p className="flex flex-1 items-center justify-center px-5 py-10 text-sm text-slate-500">
          Nothing open. Ward is watching.
        </p>
      ) : (
        <ul className="flex-1 divide-y divide-slate-100">
          {shown.map((r) => (
            <li key={r.id} className="group px-5 py-3.5 transition hover:bg-slate-50/70">
              <div className="flex items-baseline justify-between gap-3">
                <p className="min-w-0 truncate text-[13.5px] font-semibold text-ink">
                  {r.name || r.id}
                  {r.detail && <span className="ml-1.5 font-mono text-[11px] font-normal text-slate-400">{r.detail}</span>}
                </p>
                <p className="shrink-0 text-[12.5px] font-bold tabular-nums text-ink">
                  {r.costPerDay ? `${rupeesShort(r.costPerDay)}/day` : '—'}
                </p>
              </div>

              <div className="mt-2 flex items-center gap-3">
                <span className="h-2.5 flex-1">
                  <span
                    className={`block h-full rounded-r-[4px] transition-all duration-500 ${r.level === 'alert' ? 'bg-coral-500' : 'bg-amber-400'}`}
                    style={{ width: `${Math.max((r.costPerDay / worst) * 100, 2)}%` }}
                  />
                </span>
                <span className={`shrink-0 text-[10px] font-bold uppercase tracking-[0.1em] ${r.level === 'alert' ? 'text-coral-600' : 'text-amber-700'}`}>
                  {r.level}
                </span>
              </div>

              {/* Which rules this one resource is tripping — the reason twelve alerts is not twelve problems. */}
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {r.rules.map((rule) => (
                  <li key={rule} className="flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10.5px] font-medium text-slate-600">
                    <ShieldAlert size={10} className="shrink-0 text-slate-400" />
                    <span className="max-w-[18rem] truncate">{rule}</span>
                  </li>
                ))}
                <li className="text-[10.5px] font-medium text-slate-400">· oldest {r.age}</li>
              </ul>
            </li>
          ))}
          {tail.length > 0 && (
            <li>
              <Link to="/alerts" className="flex items-center justify-between gap-3 px-5 py-3 text-[12px] font-medium text-slate-500 transition hover:bg-slate-50/70 hover:text-ink">
                <span>
                  + {tail.length} more resource{tail.length === 1 ? '' : 's'}
                  <span className="ml-1.5 text-slate-400">{tail.slice(0, 3).map((r) => r.name || r.id).join(', ')}{tail.length > 3 ? '…' : ''}</span>
                </span>
                <span className="shrink-0 font-bold tabular-nums text-ink">{rupeesShort(tailCost)}/day</span>
              </Link>
            </li>
          )}
        </ul>
      )}

      <Link
        to="/alerts"
        className="group mt-auto flex items-center justify-between gap-2 border-t border-slate-100 bg-slate-50/60 px-5 py-3.5 text-xs font-semibold text-slate-500 transition hover:bg-slate-50 hover:text-arc-700"
      >
        Snooze, resolve, or tune the rules behind these
        <ArrowRight size={13} className="transition group-hover:translate-x-0.5" />
      </Link>
    </Panel>
  )
}

/* One row per resource, not per alert: the same instance tripping three rules costs what it costs
   once. Severity is the worst of its alerts; the cost is the largest figure any of them reported. */
function groupByResource(open) {
  const map = new Map()
  for (const a of open) {
    const id = a.resource?.id ?? a.resourceId
    const entry = map.get(id) ?? { id, name: a.resource?.name, detail: detailOf(a), costPerDay: 0, level: 'warning', rules: [], at: a.at }
    entry.costPerDay = Math.max(entry.costPerDay, (a.projectedMonthly ?? 0) / 30)
    if (a.level === 'alert') entry.level = 'alert'
    if (a.rule?.english && !entry.rules.includes(a.rule.english)) entry.rules.push(a.rule.english)
    if (new Date(a.at) < new Date(entry.at)) entry.at = a.at
    map.set(id, entry)
  }
  return [...map.values()]
    .map((e) => ({ ...e, age: ago(e.at) }))
    .sort((a, b) => b.costPerDay - a.costPerDay || b.rules.length - a.rules.length)
}

// The instance type sits inside the alert message; pull it out rather than printing the sentence.
function detailOf(alert) {
  return /\(([\w.]+x?\w*)\)/.exec(alert.message ?? '')?.[1] ?? null
}

function dailyCounts(alerts) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const counts = new Map()
  for (const a of alerts) {
    const d = new Date(a.at)
    d.setHours(0, 0, 0, 0)
    counts.set(d.getTime(), (counts.get(d.getTime()) ?? 0) + 1)
  }
  return Array.from({ length: DAYS }, (_, i) => {
    const d = new Date(today)
    d.setDate(d.getDate() - (DAYS - 1 - i))
    return {
      key: d.getTime(),
      count: counts.get(d.getTime()) ?? 0,
      label: d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }),
    }
  })
}

// Sequential: one hue, more alerts is darker. A quiet day is the track colour, never a second hue.
function intensity(count, peak) {
  if (!count) return 'bg-slate-100'
  const share = count / peak
  if (share > 0.66) return 'bg-arc-600'
  if (share > 0.33) return 'bg-arc-400'
  return 'bg-arc-200'
}

function ago(iso) {
  const hours = (Date.now() - new Date(iso).getTime()) / 3_600_000
  if (hours < 24) return `${Math.round(hours)}h ago`
  return `${Math.round(hours / 24)}d ago`
}
