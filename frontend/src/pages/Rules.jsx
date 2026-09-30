import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Code2 } from 'lucide-react'
import { useRules } from '../api/hooks.js'
import { ago, rupees } from '../lib/format.js'
import { Loading, PageHeader } from '../components/ui.jsx'
import RuleComposer from '../components/RuleComposer.jsx'
import YamlBlock from '../components/YamlBlock.jsx'

// SRS §2 starter rulebook, plus two that show off clarification and region rules.
const SUGGESTIONS = [
  'Stay inside the free tier',
  'Nothing runs longer than 6 hours unattended',
  'No GPU instance without an expiry tag',
  'Warn before monthly spend crosses the budget',
  'Nothing left running over a weekend',
  'Flag any resource with no owner tag',
  "Don't let anything expensive run too long",
  'No resources outside ap-south-1',
]

export default function Rules() {
  // The draft lives in the URL so links from Copilot, Detective and Guardian work even when this page is already open.
  const [params, setParams] = useSearchParams()
  const draft = params.get('draft') ?? ''
  const { data: rules, isLoading } = useRules()
  const [inspecting, setInspecting] = useState(null)

  return (
    <>
      <PageHeader
        title="Guardrails"
        subtitle="Write a rule in English. Ward compiles it, verifies it, and shows what it would do before anything is activated."
      />

      <RuleComposer
        initialText={draft}
        suggestions={SUGGESTIONS}
        onPick={(text) => setParams({ draft: text }, { replace: true })}
      />

      {isLoading ? <Loading label="Loading your guardrails…" skeleton={false} /> : <Rack rules={rules} inspecting={inspecting} setInspecting={setInspecting} />}
    </>
  )
}

/* The rulebook as a rack of instruments rather than a spreadsheet: each guardrail is a strip
   carrying its own readouts — how often it fired, how often anyone listened, what it saved,
   and a ten-segment quality meter — over a rail coloured by that quality. */
function Rack({ rules, inspecting, setInspecting }) {
  const fired = rules.reduce((s, r) => s + r.firesLast30d, 0)
  const acted = rules.reduce((s, r) => s + r.actedOn, 0)
  const avoided = rules.reduce((s, r) => s + r.savings30d, 0)

  return (
    <section className="mt-12">
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4 border-b-2 border-ink pb-4">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400">Evaluated every 15 minutes</p>
          <h2 className="mt-1.5 font-display text-[clamp(1.6rem,3.5vw,2.25rem)] font-semibold tracking-tight text-ink">
            Active guardrails
          </h2>
        </div>
        <dl className="flex items-end gap-7">
          <Readout label="Rules" value={rules.length} />
          <Readout label="Fired · 30d" value={fired} />
          <Readout label="Acted on" value={`${Math.round((acted / Math.max(fired, 1)) * 100)}%`} />
          <Readout label="Avoided" value={rupees(avoided)} accent />
        </dl>
      </div>

      <ul>
        {rules.map((r) => {
          const open = inspecting?.id === r.id
          const rate = r.firesLast30d ? Math.round((r.actedOn / r.firesLast30d) * 100) : null
          const band = QUALITY_BAND(r.quality)
          return (
            <li key={r.id} className={`group relative border-b border-slate-200/80 transition ${open ? 'bg-slate-50/70' : 'hover:bg-slate-50/50'}`}>
              <span aria-hidden className={`absolute inset-y-0 left-0 w-[3px] transition-opacity ${band.rail} ${open ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`} />

              <div className="grid items-center gap-x-6 gap-y-4 px-4 py-5 md:grid-cols-[minmax(0,1fr)_auto] md:px-5">
                <div className="min-w-0">
                  <p className="font-display text-[clamp(1.05rem,2.2vw,1.35rem)] font-semibold leading-snug tracking-tight text-ink">
                    {r.english}
                  </p>
                  <p className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] font-medium text-slate-500">
                    <span className="tabular-nums">added {ago(r.createdAt)}</span>
                    <span className="text-slate-300">·</span>
                    <span className="font-mono text-[10.5px] text-slate-500">{resourceOf(r.yaml)}</span>
                    {r.yaml && (
                      <button
                        onClick={() => setInspecting(open ? null : r)}
                        className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10.5px] font-bold text-slate-600 transition hover:border-arc-200 hover:bg-arc-50 hover:text-arc-700"
                      >
                        <Code2 size={11} /> {open ? 'Hide policy' : 'Policy'}
                      </button>
                    )}
                  </p>
                </div>

                <div className="flex flex-wrap items-end gap-x-7 gap-y-4">
                  {/* Fires, and how many of them anyone acted on. */}
                  <div className="w-36">
                    <div className="flex items-baseline justify-between text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">
                      Signal
                      <span className="font-sans text-[11px] font-bold normal-case tracking-normal tabular-nums text-ink">
                        {r.firesLast30d ? `${r.actedOn}/${r.firesLast30d}` : '—'}
                      </span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-arc-100">
                      <div className="h-full rounded-full bg-arc-500 transition-all duration-500" style={{ width: `${rate ?? 0}%` }} />
                    </div>
                    <p className="mt-1 text-[10.5px] text-slate-500">{rate == null ? 'never fired' : `${rate}% acted on`}</p>
                  </div>

                  {/* Ten segments, one per ten points — a meter, not a dial. */}
                  <div className="w-32">
                    <div className="flex items-baseline justify-between text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">
                      Quality
                      <span className={`font-sans text-[11px] font-bold normal-case tracking-normal tabular-nums ${band.text}`}>
                        {r.quality == null ? 'prov.' : `${r.quality}`}
                      </span>
                    </div>
                    <div className="mt-1.5 flex gap-[2px]">
                      {Array.from({ length: 10 }, (_, i) => (
                        <span
                          key={i}
                          className={`h-2.5 flex-1 rounded-[1px] ${i * 10 < (r.quality ?? 0) ? band.fill : band.track}`}
                        />
                      ))}
                    </div>
                    <p className="mt-1 text-[10.5px] text-slate-500">{band.label}</p>
                  </div>

                  <div className="min-w-[5.5rem] text-right">
                    <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">Avoided</p>
                    <p className="mt-0.5 font-display text-[1.45rem] font-semibold leading-none text-ink">
                      {r.savings30d ? rupees(r.savings30d) : '—'}
                    </p>
                    <p className="mt-1 text-[10.5px] text-slate-500">last 30 days</p>
                  </div>
                </div>
              </div>

              {open && (
                <div className="animate-rise grid gap-3 px-4 pb-5 md:grid-cols-[1.4fr_1fr] md:px-5">
                  <div className="rounded-2xl bg-ink p-4">
                    <div className="mb-3 flex items-center justify-between">
                      <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-white/40">Compiled policy</span>
                      <span className="rounded-md bg-white/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-white/60">c7n</span>
                    </div>
                    <YamlBlock code={r.yaml} />
                  </div>
                  {r.improvementTip && (
                    <div className="rounded-2xl border border-arc-100 bg-arc-50 p-4">
                      <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-arc-700/70">To improve</p>
                      <p className="mt-2 text-[13px] leading-relaxed text-arc-900">{r.improvementTip}</p>
                    </div>
                  )}
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function Readout({ label, value, accent }) {
  return (
    <div>
      <dt className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</dt>
      <dd className={`mt-1 font-display text-[1.35rem] font-semibold leading-none ${accent ? 'text-emerald-700' : 'text-ink'}`}>{value}</dd>
    </div>
  )
}

// Quality is a status reading, so it wears the status palette — never a categorical hue.
// The unfilled segments are a lighter step of the same ramp, so the band reads across the
// whole meter rather than only where it is filled.
const QUALITY_BAND = (q) => {
  if (q == null) return { rail: 'bg-slate-300', fill: 'bg-slate-300', track: 'bg-slate-200/70', text: 'text-slate-500', label: 'provisional' }
  if (q >= 80) return { rail: 'bg-emerald-500', fill: 'bg-emerald-500', track: 'bg-emerald-100', text: 'text-emerald-700', label: 'trustworthy' }
  if (q >= 60) return { rail: 'bg-amber-400', fill: 'bg-amber-400', track: 'bg-amber-100', text: 'text-amber-700', label: 'needs tightening' }
  return { rail: 'bg-coral-400', fill: 'bg-coral-400', track: 'bg-coral-100', text: 'text-coral-600', label: 'noisy' }
}

// The c7n resource the policy targets, pulled straight out of its YAML.
const resourceOf = (yaml) => /resource:\s*([\w.]+)/.exec(yaml ?? '')?.[1] ?? 'policy'
