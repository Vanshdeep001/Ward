import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Check, Copy, Lock, PiggyBank, Settings2, ShieldAlert, TrendingUp } from 'lucide-react'
import { useFindings } from '../api/hooks.js'
import { rupees, shortDate } from '../lib/format.js'
import { Aura, ErrorState, Loading } from '../components/ui.jsx'

/* Guardian: what Ward found without anyone writing a rule. The page leads with how many things are
   worth fixing and what they cost together; each finding is a numbered card — what's wrong, what it
   costs, the command that fixes it now, and the guardrail that stops it coming back. */

const FAMILY = {
  security: { icon: Lock, label: 'Security', chip: 'bg-coral-50 text-coral-600 ring-coral-100', aura: 'coral', num: 'text-coral-500' },
  waste: { icon: PiggyBank, label: 'Waste', chip: 'bg-amber-50 text-amber-700 ring-amber-200', aura: 'amber', num: 'text-amber-500' },
  configuration: { icon: Settings2, label: 'Configuration', chip: 'bg-arc-50 text-arc-700 ring-arc-100', aura: 'peri', num: 'text-arc-400' },
  behavioural: { icon: TrendingUp, label: 'Behavioural', chip: 'bg-violet-50 text-violet-700 ring-violet-200', aura: 'lilac', num: 'text-violet-400' },
}
const TOP = 3

export default function Guardian() {
  const { data, isLoading, error, refetch } = useFindings()
  const [showAll, setShowAll] = useState(false)

  if (isLoading) return <Loading label="Reviewing your account…" />
  if (!data) return <ErrorState error={error} onRetry={() => refetch()} />
  const findings = data ?? []
  const shown = showAll ? findings : findings.slice(0, TOP)
  const impact = findings.reduce((s, f) => s + (f.monthlyImpact || 0), 0)
  const urgent = findings.filter((f) => f.severity === 'urgent').length
  const families = Object.keys(FAMILY).map((k) => [k, findings.filter((f) => f.family === k).length]).filter(([, n]) => n)

  return (
    <>
      <header className="mb-10">
        <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400">Guardian · findings nobody wrote a rule for</p>
        <h1 className="mt-4 max-w-4xl font-display text-[clamp(2.2rem,5vw,3.6rem)] font-semibold leading-[1.03] tracking-tight text-ink">
          {findings.length ? (
            <>
              Ward found <span className="text-coral-600">{findings.length}</span> thing{findings.length === 1 ? '' : 's'} worth fixing
              {impact > 0 ? <> — <span className="text-arc-600">{rupees(impact)}</span> a month.</> : '.'}
            </>
          ) : (
            'Nothing needs fixing right now.'
          )}
        </h1>
        <div className="mt-5 flex flex-wrap items-center gap-2">
          {urgent > 0 && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-coral-500 px-3 py-1 text-[12px] font-bold text-white">
              <ShieldAlert size={13} /> {urgent} urgent — you were notified
            </span>
          )}
          {families.map(([k, n]) => {
            const fam = FAMILY[k]
            const Icon = fam.icon
            return (
              <span key={k} className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[12px] font-bold ring-1 ring-inset ${fam.chip}`}>
                <Icon size={12} /> {n} {fam.label.toLowerCase()}
              </span>
            )
          })}
        </div>
      </header>

      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <p className="text-[13px] text-slate-500">
          {showAll || findings.length <= TOP ? `All ${findings.length}` : `Top ${TOP} of ${findings.length}`} · ranked by impact × confidence
        </p>
        {findings.length > TOP && (
          <div className="relative grid grid-cols-2 rounded-2xl border border-slate-200/80 bg-white p-1 shadow-[0_1px_2px_rgb(15_23_42/0.04)]">
            <span
              aria-hidden
              className="absolute inset-y-1 left-1 w-[calc(50%-0.25rem)] rounded-xl bg-ink transition-transform duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]"
              style={{ transform: `translateX(${showAll ? 100 : 0}%)` }}
            />
            {[['Top 3', false], ['All', true]].map(([label, all]) => (
              <button key={label} type="button" onClick={() => setShowAll(all)} className={`relative z-10 px-4 py-1.5 text-[12.5px] font-bold transition-colors ${showAll === all ? 'text-white' : 'text-slate-500 hover:text-ink'}`}>
                {label}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-5">
        {shown.map((f, i) => <Finding key={f.id} f={f} rank={i + 1} />)}
      </div>
    </>
  )
}

function Finding({ f, rank }) {
  const fam = FAMILY[f.family] ?? FAMILY.configuration
  const Icon = fam.icon
  const urgent = f.severity === 'urgent'
  return (
    <article
      className={`animate-rise group/aura relative overflow-hidden rounded-[28px] border bg-white shadow-[0_1px_2px_rgb(15_23_42/0.04),0_22px_48px_-34px_rgb(23_23_60/0.5)] ${urgent ? 'border-coral-200' : 'border-slate-200/70'}`}
      style={{ animationDelay: `${rank * 60}ms` }}
    >
      <div className="grid gap-x-7 gap-y-4 p-6 md:grid-cols-[auto_1fr_auto] md:p-7">
        <p className={`font-display text-[3.2rem] font-semibold leading-[0.85] ${fam.num}`}>{String(rank).padStart(2, '0')}</p>

        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11.5px] font-bold ring-1 ring-inset ${fam.chip}`}>
              <Icon size={12} /> {fam.label}
            </span>
            {urgent && <span className="rounded-full bg-coral-500 px-2.5 py-0.5 text-[11px] font-bold text-white">Notified immediately</span>}
            {f.confidence != null && <span className="text-[12px] font-semibold text-slate-400">{Math.round(f.confidence * 100)}% confident</span>}
          </div>
          <h2 className="mt-2.5 font-display text-[clamp(1.35rem,2.4vw,1.8rem)] font-semibold leading-[1.15] tracking-tight text-ink">{f.title}</h2>
          <p className="mt-1.5 max-w-2xl text-[14.5px] leading-relaxed text-slate-600">{f.detail}</p>
        </div>

        <div className="md:text-right">
          {f.monthlyImpact ? (
            <>
              <p className="font-display text-[2.1rem] font-semibold leading-none tabular-nums text-coral-600">{rupees(f.monthlyImpact)}</p>
              <p className="mt-1 text-[10.5px] font-bold uppercase tracking-[0.16em] text-slate-400">a month</p>
            </>
          ) : (
            <p className="text-[12px] font-semibold text-slate-400">{f.family === 'security' ? 'A risk, not a cost' : 'No direct cost'}</p>
          )}
        </div>
      </div>

      <div className="space-y-4 px-6 pb-6 md:px-7 md:pl-[6.6rem]">
        {f.evidence && (
          <div className="rounded-2xl bg-violet-50/70 p-4 ring-1 ring-inset ring-violet-100">
            <p className="text-[10.5px] font-bold uppercase tracking-[0.16em] text-violet-700">Evidence</p>
            <ul className="mt-2 space-y-1 text-[13.5px] text-slate-700">
              {f.evidence.map((e) => (
                <li key={e.date}>Weekend of {shortDate(e.date)} — <span className="font-mono text-[12px]">{e.resourceId}</span> ran {e.hours}h</li>
              ))}
            </ul>
          </div>
        )}

        {f.fix && <FixCommand command={f.fix} />}

        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-slate-100 pt-4">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-[12px] text-slate-400">
            {f.resourceIds.slice(0, 3).map((id) => (
              <span key={id} className="rounded-md bg-slate-50 px-1.5 py-0.5 font-mono text-[11px] text-slate-500 ring-1 ring-inset ring-slate-200">{id}</span>
            ))}
            {f.resourceIds.length > 3 && <span className="font-semibold">+{f.resourceIds.length - 3} more</span>}
            <span className="ml-1">· found by <span className="font-mono text-[11px]">{f.source}</span></span>
          </div>
          {f.suggestedRule && (
            <Link
              to={`/rules?draft=${encodeURIComponent(f.suggestedRule)}`}
              className="group inline-flex max-w-full items-center gap-3 rounded-full bg-arc-600 py-1.5 pl-5 pr-1.5 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.2),0_12px_26px_-12px_rgb(49_57_251/0.8)] transition hover:bg-arc-700"
            >
              <span className="min-w-0 leading-tight">
                <span className="block text-[10px] font-bold uppercase tracking-[0.14em] text-white/70">Stop it recurring</span>
                <span className="block truncate text-[13.5px] font-semibold">“{f.suggestedRule}”</span>
              </span>
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-white/20 transition group-hover:translate-x-0.5">
                <ArrowRight size={15} strokeWidth={2.5} />
              </span>
            </Link>
          )}
        </div>
      </div>

      <Aura color={fam.aura} icon={Icon} size={140} />
    </article>
  )
}

// The command that fixes it now — light, like the rest of the page, with copy feedback.
function FixCommand({ command }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="rounded-2xl bg-paper ring-1 ring-inset ring-slate-200/80">
      <div className="flex items-center justify-between px-4 pt-2.5">
        <span className="text-[10.5px] font-bold uppercase tracking-[0.16em] text-slate-400">Fix it now</span>
        <button
          type="button"
          onClick={() => { navigator.clipboard?.writeText(command); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11.5px] font-bold text-slate-500 transition hover:bg-white hover:text-ink"
        >
          {copied ? <><Check size={12} className="text-emerald-600" /> Copied</> : <><Copy size={12} /> Copy</>}
        </button>
      </div>
      <code className="block overflow-x-auto whitespace-nowrap px-4 pb-3 pt-1.5 font-mono text-[12.5px] text-ink">
        <span className="select-none text-arc-500">$ </span>{command}
      </code>
    </div>
  )
}
