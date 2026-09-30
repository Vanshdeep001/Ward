import { useEffect, useState } from 'react'
import { AlertOctagon, CheckCircle2, Code2, EyeOff, Gauge, GitMerge, Layers, Lightbulb, RefreshCw, Zap } from 'lucide-react'
import { useConflicts, useRules } from '../api/hooks.js'
import { Aura, ErrorState, Loading } from '../components/ui.jsx'
import YamlBlock from '../components/YamlBlock.jsx'

/* Rule health, told with pictures that carry the argument rather than decorate it:

   - the rulebook as one strip chart — every rule's quality on a 0–100 scale over its bands, with the
     average marked — so the weak rule is visible before any text is read;
   - every conflict drawn as the relationship it is: an empty circle for a rule that matches nothing,
     A inside B for redundancy, a Venn with the shared resources counted in the lens for an overlap,
     two circles held apart for a contradiction;
   - every rule's five quality dimensions as a small bar chart, always shown. */

const CATEGORY = {
  contradiction: { label: 'Contradiction', icon: AlertOctagon, tone: 'text-coral-600', ring: 'ring-coral-200', aura: 'coral' },
  subsumption: { label: 'Redundant', icon: Layers, tone: 'text-amber-700', ring: 'ring-amber-200', aura: 'amber' },
  overlap: { label: 'Overlap', icon: GitMerge, tone: 'text-amber-700', ring: 'ring-amber-200', aura: 'peach' },
  dead: { label: 'Dead rule', icon: EyeOff, tone: 'text-slate-500', ring: 'ring-slate-200', aura: 'slate' },
}
const FILTERS = ['all', 'contradiction', 'subsumption', 'overlap', 'dead']
const DIMENSIONS = [
  ['specificity', 'Specific'],
  ['verifiability', 'Verified'],
  ['actionability', 'Actionable'],
  ['signalRate', 'Signal'],
  ['stability', 'Stable'],
]
const SPRING = 'ease-[cubic-bezier(0.32,0.72,0,1)]'

// Quality is a status reading, so it wears the status palette, always with its word beside it.
function band(q) {
  if (q == null) return { word: 'Provisional', text: 'text-slate-400', bar: 'bg-slate-300', dot: 'bg-slate-300', aura: 'slate' }
  if (q >= 80) return { word: 'Trustworthy', text: 'text-emerald-600', bar: 'bg-emerald-500', dot: 'bg-emerald-500', aura: 'green' }
  if (q >= 60) return { word: 'Needs tightening', text: 'text-amber-600', bar: 'bg-amber-400', dot: 'bg-amber-400', aura: 'amber' }
  return { word: 'Noisy', text: 'text-coral-600', bar: 'bg-coral-500', dot: 'bg-coral-500', aura: 'coral' }
}

const WORDS = ['No', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine']
const say = (n) => WORDS[n] ?? String(n)

export default function RuleHealth() {
  const { data: conflicts, isLoading: loadingConflicts, refetch, isFetching } = useConflicts()
  const { data: rules, isLoading: loadingRules, error: rulesError, refetch: refetchRules } = useRules()
  const [filter, setFilter] = useState('all')
  const [applied, setApplied] = useState({})

  if (loadingConflicts || loadingRules) return <Loading label="Evaluating your rules against the account…" />
  if (!conflicts || !rules) return <ErrorState error={rulesError} onRetry={() => { refetch(); refetchRules() }} />

  const scored = rules.filter((r) => r.quality != null) // new rules stay provisional for two weeks (§22.1)
  const avg = scored.length ? Math.round(scored.reduce((s, r) => s + r.quality, 0) / scored.length) : null
  const count = (cat) => conflicts.filter((c) => c.category === cat).length
  const doubled = conflicts.filter((c) => c.category === 'overlap' || c.category === 'subsumption').reduce((n, c) => n + (c.affected ?? 0), 0)
  const shown = conflicts.filter((c) => filter === 'all' || c.category === filter)

  return (
    <>
      {/* ── Verdict ───────────────────────────────────────────────────────── */}
      <header className="grid gap-10 lg:grid-cols-[1.1fr_1fr] lg:items-end">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400">Rule health · checked on activation, nightly, and on demand</p>
          <h1 className="mt-4 font-display text-[clamp(2.2rem,4.8vw,3.5rem)] font-semibold leading-[1.04] tracking-tight text-ink">
            {avg == null ? (
              'Your rules are still provisional.'
            ) : (
              <>
                Your rulebook scores <span className={band(avg).text}>{avg}</span>.
              </>
            )}
            <span className="block text-slate-400">{verdict(count, doubled)}</span>
          </h1>
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="mt-7 inline-flex items-center gap-2.5 rounded-full bg-ink py-2 pl-2 pr-5 text-[14px] font-semibold text-white shadow-[0_14px_30px_-14px_rgb(0_0_0/0.6)] transition hover:bg-black disabled:opacity-60"
          >
            <span className="grid h-8 w-8 place-items-center rounded-full bg-white/10">
              <RefreshCw size={15} className={isFetching ? 'animate-spin' : ''} />
            </span>
            {isFetching ? 'Checking every rule…' : 'Re-check my rules'}
          </button>
        </div>

        <Rulebook rules={rules} />
      </header>

      {/* ── The four numbers ──────────────────────────────────────────────── */}
      <dl className="mt-12 grid grid-cols-2 overflow-hidden rounded-3xl border border-slate-200/70 bg-white shadow-[0_1px_2px_rgb(15_23_42/0.04),0_20px_44px_-32px_rgb(23_23_60/0.45)] md:grid-cols-4">
        <Readout label="Conflicts found" value={conflicts.length} note="across every pair of rules" />
        <Readout label="Contradictions" value={count('contradiction')} note={count('contradiction') ? 'rules that cannot both hold' : 'no deadlocks'} tone={count('contradiction') ? 'text-coral-600' : 'text-emerald-600'} />
        <Readout label="Dead rules" value={count('dead')} note="match nothing in this account" tone={count('dead') ? 'text-slate-500' : 'text-emerald-600'} />
        <Readout label="Alerted twice" value={doubled} note={`resource${doubled === 1 ? '' : 's'} caught by two rules`} tone={doubled ? 'text-amber-600' : 'text-emerald-600'} />
      </dl>

      {/* ── Diagnoses ─────────────────────────────────────────────────────── */}
      <section className="mt-16">
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div>
            <h2 className="font-display text-[2rem] font-semibold tracking-tight text-ink">Diagnoses</h2>
            <p className="mt-1 text-[14px] text-slate-500">Measured by what each rule actually matches in your account — not by how it is worded.</p>
          </div>
          <Filter value={filter} onChange={setFilter} counts={{ all: conflicts.length, ...Object.fromEntries(FILTERS.slice(1).map((f) => [f, count(f)])) }} />
        </div>

        <div className="mt-6 space-y-5">
          {shown.map((c) => (
            <Diagnosis key={c.id} c={c} applied={applied[c.id]} onApply={() => setApplied((a) => ({ ...a, [c.id]: true }))} />
          ))}
          {shown.length === 0 && (
            <div className="rounded-3xl border border-dashed border-slate-300 px-6 py-14 text-center">
              <CheckCircle2 size={26} className="mx-auto text-emerald-500" />
              <p className="mt-3 font-display text-[1.6rem] font-semibold text-ink">Nothing to diagnose.</p>
              <p className="mt-1 text-[14px] text-slate-500">These rules are mutually consistent.</p>
            </div>
          )}
        </div>
      </section>

      {/* ── Report cards ──────────────────────────────────────────────────── */}
      <section className="mt-16">
        <h2 className="font-display text-[2rem] font-semibold tracking-tight text-ink">Report cards</h2>
        <p className="mt-1 text-[14px] text-slate-500">
          Specificity 25 · Verifiability 20 · Actionability 20 · Signal rate 20 · Stability 15. Advice only — a low score never blocks a rule.
        </p>
        <div className="mt-6 grid gap-5 lg:grid-cols-2">
          {rules.map((r, i) => (
            <ReportCard key={r.id} rule={r} index={i + 1} />
          ))}
        </div>
      </section>
    </>
  )
}

function verdict(count, doubled) {
  const contra = count('contradiction')
  const dead = count('dead')
  if (contra) return `${say(contra)} pair${contra === 1 ? '' : 's'} of rules contradict${contra === 1 ? 's' : ''} each other.`
  if (dead) return `${say(dead)} rule${dead === 1 ? ' is' : 's are'} watching nothing.`
  if (doubled) return `${say(doubled)} resource${doubled === 1 ? ' gets' : 's get'} alerted twice.`
  return 'Nothing contradicts, nothing overlaps.'
}

/* ── The rulebook, as one chart ──────────────────────────────────────────── */

const GOAL = 80 // where "trustworthy" begins

// Each band's bar: a gradient capsule with a glow in its own colour.
const CAPSULE = {
  Trustworthy: { fill: 'bg-gradient-to-t from-emerald-600 to-emerald-300', glow: 'shadow-[0_12px_26px_-8px_rgb(16_185_129/0.6)]', ghost: 'border-emerald-300', gap: 'text-emerald-600' },
  'Needs tightening': { fill: 'bg-gradient-to-t from-amber-500 to-amber-300', glow: 'shadow-[0_12px_26px_-8px_rgb(245_158_11/0.65)]', ghost: 'border-amber-300', gap: 'text-amber-600' },
  Noisy: { fill: 'bg-gradient-to-t from-coral-600 to-coral-400', glow: 'shadow-[0_12px_26px_-8px_rgb(238_93_88/0.6)]', ghost: 'border-coral-300', gap: 'text-coral-600' },
}

/* The whole rulebook in one chart. Beyond each score it shows the distance still to go: a dashed
   ghost above every bar, rising to the goal line, labelled with how many points it would take. */
function Rulebook({ rules }) {
  const [hover, setHover] = useState(null)
  const [grown, setGrown] = useState(false)
  useEffect(() => {
    const frame = requestAnimationFrame(() => setGrown(true)) // bars rise into place once, on arrival
    return () => cancelAnimationFrame(frame)
  }, [])
  const focus = hover != null ? rules[hover] : null

  return (
    <figure className="group/aura relative overflow-hidden rounded-3xl border border-slate-200/70 bg-white p-5 shadow-[0_1px_2px_rgb(15_23_42/0.04),0_24px_50px_-30px_rgb(23_23_60/0.5)]">
      {/* One line: the title, or — while hovering — the rule under the pointer. */}
      <figcaption className="flex h-7 items-center justify-between gap-3">
        {focus ? (
          <p className="min-w-0 truncate text-[13px] font-semibold text-ink">
            <span className={`mr-1.5 text-[10.5px] font-bold uppercase tracking-[0.14em] ${band(focus.quality).text}`}>R{hover + 1}</span>
            “{focus.english}”
          </p>
        ) : (
          <p className="text-[10.5px] font-bold uppercase tracking-[0.16em] text-slate-400">Quality of every rule</p>
        )}
        <span className="shrink-0 rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-bold text-emerald-700 ring-1 ring-inset ring-emerald-200">
          goal {GOAL}
        </span>
      </figcaption>

      {/* The plot holds only the bars, their ghosts and the goal line — every label lives outside it. */}
      <div className="relative mt-4 h-32">
        <div className="absolute inset-x-0 top-0 h-[20%] rounded-t-lg bg-gradient-to-b from-emerald-100/70 to-transparent" />
        <div className="absolute inset-x-0 border-t-2 border-emerald-400/70" style={{ bottom: `${GOAL}%` }} />

        <div className="relative flex h-full items-end justify-around px-6">
          {rules.map((r, i) => {
            const style = CAPSULE[band(r.quality).word]
            const score = r.quality
            return (
              <button
                key={r.id}
                type="button"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                aria-label={`${r.english}: ${score ?? 'provisional'}${score != null && score < GOAL ? `, ${GOAL - score} points from trustworthy` : ''}`}
                className={`relative flex h-full w-10 items-end justify-center transition-opacity duration-300 ${hover != null && hover !== i ? 'opacity-35' : ''}`}
              >
                {score == null ? (
                  <span className="h-full w-6 rounded-t-[7px] border-2 border-dashed border-slate-300" />
                ) : (
                  <>
                    {score < GOAL && (
                      <span
                        className={`absolute w-6 rounded-t-[7px] border-2 border-b-0 border-dashed ${style.ghost} transition-opacity delay-700 duration-500 ${grown ? 'opacity-100' : 'opacity-0'}`}
                        style={{ bottom: `${score}%`, height: `${GOAL - score}%` }}
                      />
                    )}
                    <span
                      className={`relative w-6 rounded-t-[7px] ${style.fill} ${style.glow} transition-[height] duration-1000 ${SPRING} motion-reduce:transition-none`}
                      style={{ height: grown ? `${score}%` : '0%', transitionDelay: grown ? `${i * 90}ms` : '0ms' }}
                    >
                      <span className="absolute inset-y-1.5 left-1 w-[3px] rounded-full bg-white/40" />
                      <span className="absolute inset-x-0 top-1 text-center text-[10.5px] font-bold tabular-nums text-white">{score}</span>
                    </span>
                  </>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {/* Under each bar: its name, and how far it is from the goal. */}
      <div className="mt-2 flex justify-around px-6">
        {rules.map((r, i) => {
          const gap = r.quality == null ? null : GOAL - r.quality
          return (
            <span key={r.id} className="flex w-10 flex-col items-center leading-tight">
              <span className={`font-mono text-[11px] font-bold ${hover === i ? 'text-ink' : 'text-slate-400'}`}>R{i + 1}</span>
              <span className={`text-[10px] font-bold tabular-nums ${gap == null ? 'text-slate-300' : gap > 0 ? CAPSULE[band(r.quality).word].gap : 'text-emerald-600'}`}>
                {gap == null ? '—' : gap > 0 ? `+${gap}` : '✓'}
              </span>
            </span>
          )
        })}
      </div>

      <p className="mt-3 flex flex-wrap items-center gap-x-3.5 gap-y-1 border-t border-slate-100 pt-2.5 text-[10.5px] font-semibold text-slate-500">
        {[80, 60, 0].map((q) => (
          <span key={q} className="flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full ${band(q).dot}`} /> {band(q).word}
          </span>
        ))}
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-t-sm border border-b-0 border-dashed border-slate-400" /> +N to goal
        </span>
      </p>
      <Aura color="arc" />
    </figure>
  )
}

function Readout({ label, value, note, tone = 'text-ink' }) {
  return (
    <div className="border-slate-100 px-6 py-5 [&:not(:first-child)]:border-l">
      <dt className="text-[10.5px] font-bold uppercase tracking-[0.16em] text-slate-400">{label}</dt>
      <dd className={`mt-2 font-display text-[2.6rem] font-semibold leading-none ${tone}`}>{value}</dd>
      <p className="mt-2 text-[12px] text-slate-500">{note}</p>
    </div>
  )
}

function Filter({ value, onChange, counts }) {
  return (
    <div className="flex flex-wrap gap-1 rounded-2xl border border-slate-200/80 bg-white p-1 shadow-[0_1px_2px_rgb(15_23_42/0.04)]">
      {FILTERS.map((f) => (
        <button
          key={f}
          type="button"
          onClick={() => onChange(f)}
          aria-pressed={value === f}
          className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-[12.5px] font-bold transition-colors duration-300 ${
            value === f ? 'bg-ink text-white' : 'text-slate-500 hover:bg-slate-50 hover:text-ink'
          }`}
        >
          {f === 'all' ? 'All' : CATEGORY[f].label}
          <span className={`rounded-md px-1 text-[10.5px] tabular-nums ${value === f ? 'bg-white/15' : 'bg-slate-100'}`}>{counts[f] ?? 0}</span>
        </button>
      ))}
    </div>
  )
}

/* ── One diagnosis ───────────────────────────────────────────────────────── */

function Diagnosis({ c, applied, onApply }) {
  const meta = CATEGORY[c.category] ?? CATEGORY.dead
  const Icon = meta.icon
  return (
    <article className="group/aura relative grid overflow-hidden rounded-3xl border border-slate-200/70 bg-white shadow-[0_1px_2px_rgb(15_23_42/0.04),0_20px_44px_-32px_rgb(23_23_60/0.45)] md:grid-cols-[250px_1fr]">
      {/* The picture is the explanation. */}
      <div className="flex items-center justify-center border-b border-slate-100 bg-gradient-to-br from-paper to-slate-50 p-6 md:border-b-0 md:border-r">
        <Relation c={c} />
      </div>

      <div className="p-6">
        <p className={`flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-[0.16em] ${meta.tone}`}>
          <Icon size={13} /> {meta.label}
          {c.severity === 'critical' && <span className="ml-1 rounded bg-coral-500 px-1.5 py-px text-[9.5px] text-white">critical</span>}
        </p>
        <h3 className="mt-2 font-display text-[1.45rem] font-semibold leading-tight tracking-tight text-ink">{c.title}</h3>
        <p className="mt-2 text-[14px] leading-relaxed text-slate-600">{c.detail}</p>

        <div className="mt-4 flex flex-wrap gap-2">
          <RuleChip letter="A" english={c.ruleA?.english} />
          {c.ruleB && <RuleChip letter="B" english={c.ruleB.english} />}
        </div>

        <p className="mt-4 text-[13px] text-slate-500">
          <span className="font-semibold text-slate-700">Impact · </span>
          {c.impact}
        </p>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-emerald-50/70 px-4 py-3 ring-1 ring-inset ring-emerald-200/70">
          <p className="flex min-w-0 flex-1 items-start gap-2 text-[13.5px] text-emerald-900">
            <Lightbulb size={15} className="mt-0.5 shrink-0 text-emerald-600" />
            {c.suggestion}
          </p>
          {applied ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-[12px] font-bold text-emerald-700 ring-1 ring-emerald-200">
              <CheckCircle2 size={13} /> Queued for review
            </span>
          ) : (
            <button
              type="button"
              onClick={onApply}
              className="rounded-full bg-ink px-4 py-2 text-[12.5px] font-bold text-white transition hover:bg-black"
            >
              {c.actionText}
            </button>
          )}
        </div>
      </div>
      <Aura color={meta.aura} icon={Icon} />
    </article>
  )
}

function RuleChip({ letter, english }) {
  return (
    <span className="inline-flex max-w-full items-center gap-2 rounded-xl border border-slate-200 bg-paper/70 py-1.5 pl-1.5 pr-3 text-[12.5px] font-medium text-slate-700">
      <span className="grid h-5 w-5 shrink-0 place-items-center rounded-md bg-ink font-mono text-[10.5px] font-bold text-white">{letter}</span>
      <span className="truncate">“{english}”</span>
    </span>
  )
}

/* Each relationship, drawn. Letters match the rule chips beside it. */
function Relation({ c }) {
  const n = c.affected ?? 0
  const clip = `lens-${c.id}`
  const label = 'fill-slate-500 text-[11px] font-bold'
  return (
    <svg viewBox="0 0 200 140" className="w-full max-w-[210px]" role="img" aria-label={`${CATEGORY[c.category]?.label}: ${n} resources`}>
      {c.category === 'dead' && (
        <>
          <circle cx="100" cy="68" r="46" className="fill-white stroke-slate-300" strokeWidth="2" strokeDasharray="5 5" />
          <text x="100" y="74" textAnchor="middle" className="fill-slate-300 font-display text-[36px] font-semibold">0</text>
          <text x="100" y="94" textAnchor="middle" className="fill-slate-400 text-[9.5px] font-bold uppercase tracking-widest">matches</text>
          <text x="100" y="134" textAnchor="middle" className="fill-slate-400 text-[10px]">watching nothing</text>
        </>
      )}

      {c.category === 'subsumption' && (
        <>
          <circle cx="100" cy="68" r="58" className="fill-arc-50 stroke-arc-300" strokeWidth="1.5" />
          <circle cx="116" cy="76" r="28" className="fill-amber-100 stroke-amber-400" strokeWidth="1.5" />
          <text x="116" y="82" textAnchor="middle" className="fill-amber-700 font-display text-[20px] font-semibold">{n}</text>
          <text x="52" y="38" className={label}>B</text>
          <text x="108" y="56" className="fill-amber-700 text-[11px] font-bold">A</text>
          <text x="100" y="138" textAnchor="middle" className="fill-slate-400 text-[10px]">A adds nothing B doesn’t</text>
        </>
      )}

      {c.category === 'overlap' && (
        <>
          <defs>
            <clipPath id={clip}>
              <circle cx="78" cy="66" r="44" />
            </clipPath>
          </defs>
          <circle cx="78" cy="66" r="44" className="fill-arc-50 stroke-arc-300" strokeWidth="1.5" />
          <circle cx="122" cy="66" r="44" className="fill-violet-50/60 stroke-violet-300" strokeWidth="1.5" />
          <circle cx="122" cy="66" r="44" clipPath={`url(#${clip})`} className="fill-amber-200/80" />
          <text x="100" y="72" textAnchor="middle" className="fill-amber-800 font-display text-[20px] font-semibold">{n}</text>
          <text x="50" y="70" className={label}>A</text>
          <text x="142" y="70" className={label}>B</text>
          <text x="100" y="134" textAnchor="middle" className="fill-slate-400 text-[10px]">alerted twice</text>
        </>
      )}

      {c.category === 'contradiction' && (
        <>
          <circle cx="54" cy="66" r="38" className="fill-arc-50 stroke-arc-300" strokeWidth="1.5" />
          <circle cx="146" cy="66" r="38" className="fill-coral-50 stroke-coral-300" strokeWidth="1.5" />
          <circle cx="100" cy="66" r="13" className="fill-coral-500" />
          <path d="M94 60l12 12M106 60l-12 12" className="stroke-white" strokeWidth="2.5" strokeLinecap="round" />
          <text x="54" y="71" textAnchor="middle" className={label}>A</text>
          <text x="146" y="71" textAnchor="middle" className={label}>B</text>
          <text x="100" y="130" textAnchor="middle" className="fill-slate-400 text-[10px]">can’t both hold</text>
        </>
      )}
    </svg>
  )
}

/* ── One rule's report card ──────────────────────────────────────────────── */

function ReportCard({ rule, index }) {
  const [showPolicy, setShowPolicy] = useState(false)
  const b = band(rule.quality)
  const bd = rule.breakdown
  const actedPct = rule.firesLast30d ? Math.round((rule.actedOn / rule.firesLast30d) * 100) : null

  return (
    <article className="group/aura relative flex flex-col overflow-hidden rounded-3xl border border-slate-200/70 bg-white p-6 shadow-[0_1px_2px_rgb(15_23_42/0.04),0_20px_44px_-32px_rgb(23_23_60/0.45)]">
      <div className="flex items-start gap-5">
        <div className="shrink-0">
          <p className={`font-display text-[3.2rem] font-semibold leading-[0.85] ${b.text}`}>{rule.quality ?? '—'}</p>
          <p className="mt-2 font-mono text-[10.5px] font-bold text-slate-400">R{index} / 100</p>
        </div>
        <div className="min-w-0">
          <p className={`flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-[0.16em] ${b.text}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${b.dot}`} /> {b.word}
          </p>
          <h3 className="mt-1.5 font-display text-[1.25rem] font-semibold leading-snug tracking-tight text-ink">“{rule.english}”</h3>
          <p className="mt-1.5 text-[12.5px] text-slate-500">
            Fired {rule.firesLast30d}× in 30 days
            {actedPct != null && ` · ${rule.actedOn} acted on (${actedPct}%)`}
          </p>
        </div>
      </div>

      {bd ? (
        <div className="mt-6 flex items-end justify-between gap-2 rounded-2xl bg-paper/80 px-4 pb-3 pt-4 ring-1 ring-inset ring-slate-200/70">
          {DIMENSIONS.map(([key, label]) => {
            const d = bd[key]
            const pct = Math.round((d.score / d.max) * 100)
            return (
              <div key={key} title={`${label}: ${d.score}/${d.max} — ${d.note}`} className="flex flex-1 flex-col items-center gap-1.5">
                <span className="text-[10.5px] font-bold tabular-nums text-slate-500">
                  {d.score}<span className="text-slate-300">/{d.max}</span>
                </span>
                <span className="flex h-14 w-5 items-end overflow-hidden rounded-[5px] bg-slate-200/70">
                  <span className={`w-full rounded-t-[4px] transition-all duration-700 ${SPRING} ${band(pct).bar}`} style={{ height: `${pct}%` }} />
                </span>
                <span className="text-[9.5px] font-bold uppercase tracking-wide text-slate-400">{label}</span>
              </div>
            )
          })}
        </div>
      ) : (
        <p className="mt-6 rounded-2xl border border-dashed border-slate-300 px-4 py-6 text-center text-[13px] text-slate-500">
          Scored once it has two weeks of history — a signal rate from two alerts would be a guess.
        </p>
      )}

      {rule.improvementTip && (
        <p className="mt-4 flex items-start gap-2 text-[13px] leading-relaxed text-slate-600">
          <Zap size={14} className="mt-0.5 shrink-0 text-amber-500" />
          {rule.improvementTip}
        </p>
      )}

      {rule.yaml && (
        <div className="mt-auto pt-4">
          <button
            type="button"
            onClick={() => setShowPolicy((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-3 py-1 text-[11.5px] font-bold text-slate-600 transition hover:border-arc-200 hover:bg-arc-50 hover:text-arc-700"
          >
            <Code2 size={12} /> {showPolicy ? 'Hide policy' : 'Policy'}
          </button>
          {showPolicy && (
            <div className="animate-rise mt-3 rounded-2xl bg-ink p-4">
              <YamlBlock code={rule.yaml} />
            </div>
          )}
        </div>
      )}
      <Aura color={b.aura} icon={Gauge} />
    </article>
  )
}
